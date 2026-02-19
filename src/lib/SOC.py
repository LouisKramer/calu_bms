# SOC.py - Updated with Coulomb Efficiency + SoH estimation (Feb 2026)
import asyncio
import time
import ujson as json
import os
from collections import deque
from common.logger import Logger
from common.common import soc_config

log_soc = Logger()
# =============================================================================
# Persistence (extended with SoH data)
# =============================================================================
def save_state(estimator, path="soc_state.json"):
    try:
        log_soc.info("Saving SOC + SoH state")
        state = {
            "soc": estimator.soc,
            "soh": estimator.soh,
            "total_throughput_ah": estimator.total_throughput_ah,
            "last_time": time.time(),
            "relaxed_start_time": estimator.relaxed_start_time,
            "voltage_history": list(estimator.voltage_history),
            "last_voltage": estimator.last_voltage,
            "last_temp": estimator.last_temp
        }
        with open(path, "w") as f:
            f.write(json.dumps(state))
    except Exception as e:
        log_soc.error(f"SOC save failed: {e}")


def load_state(estimator, path="soc_state.json"):
    if path not in os.listdir():
        return False
    try:
        with open(path, "r") as f:
            state = json.loads(f.read())

        estimator.soc = max(0.0, min(100.0, state.get("soc", estimator.soc)))
        estimator.soh = max(70.0, min(100.0, state.get("soh", estimator.soh)))
        estimator.total_throughput_ah = state.get("total_throughput_ah", 0.0)
        estimator.relaxed_start_time = state.get("relaxed_start_time")
        estimator.voltage_history = deque(state.get("voltage_history", [])[-10:], 10)
        estimator.last_voltage = state.get("last_voltage")
        estimator.last_temp = state.get("last_temp")
        estimator.last_time = time.time()   # prevent huge dt after reboot

        log_soc.info(f"SOC/SoH restored: {estimator.soc}% | SoH {estimator.soh}%")
        return True
    except Exception as e:
        log_soc.error(f"SOC load failed: {e}")
        return False


async def autosave_task(estimator, interval=300):
    while True:
        await asyncio.sleep(interval)
        save_state(estimator)


# =============================================================================
# BatterySOC - with Coulomb Efficiency + SoH
# =============================================================================
class BatterySOC:
    def __init__(self, cfg=None):
        self.cfg = cfg or soc_config()

        # Voltage-SOC table (per cell)
        self.default_per_cell = [
            (3.60, 100.0), (3.40, 95.0), (3.35, 80.0), (3.325, 60.0),
            (3.30, 40.0), (3.275, 20.0), (3.20, 10.0), (2.50, 0.0)
        ]
        self.num_cells = 0
        self.pack_table = None

        # Runtime state
        self.soc = float(self.cfg.initial_soc)
        self.soh = 100.0
        self.total_throughput_ah = 0.0          # lifetime Ah (used for SoH)
        self.last_time = time.time()
        self.last_voltage = None
        self.last_temp = 25.0
        self.relaxed_start_time = None
        self.voltage_history = deque([], 10)

        # Load persisted state
        if not load_state(self, "soc_state.json"):
            log_soc.info("No saved state → starting fresh")

    def _build_pack_table(self):
        self.pack_table = [(v * self.num_cells, soc) for v, soc in self.default_per_cell]

    def _get_compensated_ir(self, temp):
        delta_t = temp - self.cfg.ir_ref_temp
        factor = 1.0 + (self.cfg.ir_temp_coeff * delta_t)
        return self.cfg.cell_ir * self.num_cells * factor

    def _interpolate_soc(self, ocv):
        if self.pack_table is None:
            return 50.0
        table = self.pack_table
        if ocv >= table[0][0]: return 100.0
        if ocv <= table[-1][0]: return 0.0
        for i in range(len(table) - 1):
            v1, soc1 = table[i]
            v2, soc2 = table[i + 1]
            if v2 <= ocv <= v1:
                return soc1 + (soc2 - soc1) * (ocv - v1) / (v2 - v1)
        return 0.0

    def _estimate_ocv(self, voltage, current, temp):
        return voltage + current * self._get_compensated_ir(temp)

    def _is_voltage_stable(self):
        if len(self.voltage_history) < 5:
            return False
        return max(self.voltage_history) - min(self.voltage_history) < self.cfg.voltage_stable_threshold

    def _calculate_cycles(self):
        """Equivalent full cycles = total throughput / (2 × nominal capacity)"""
        return round(self.total_throughput_ah / (2 * self.cfg.capacity_ah), 1)

    def update(self, current: float, voltage: float, temperature: float, nr_cells: int):
        """Main update – now includes Coulomb Efficiency and SoH"""
        now = time.time()
        dt = max(0.01, now - self.last_time)

        if self.num_cells != nr_cells or self.pack_table is None:
            self.num_cells = nr_cells
            self._build_pack_table()

        # ====================== COULOMB COUNTING WITH EFFICIENCY ======================
        ah_raw = current * dt / 3600.0

        if current > 0:   # charging
            effective_ah = ah_raw * self.cfg.charge_efficiency
        else:             # discharging
            effective_ah = ah_raw / self.cfg.discharge_efficiency

        coulomb_soc = self.soc + (effective_ah / self.cfg.capacity_ah) * 100.0
        coulomb_soc = max(0.0, min(100.0, coulomb_soc))

        # Accumulate lifetime throughput (absolute value)
        self.total_throughput_ah += abs(ah_raw)

        # ====================== OCV CORRECTION ======================
        ocv = self._estimate_ocv(voltage, current, temperature)
        self.voltage_history.append(voltage)

        low_i = abs(current) < self.cfg.current_threshold
        stable = self._is_voltage_stable()

        if low_i and stable:
            if self.relaxed_start_time is None:
                self.relaxed_start_time = now
            elif now - self.relaxed_start_time >= self.cfg.relaxed_hold_time:
                ocv_soc = self._interpolate_soc(ocv)
                coulomb_soc = coulomb_soc * 0.8 + ocv_soc * 0.2
        else:
            self.relaxed_start_time = None
            ocv_soc = self._interpolate_soc(ocv)
            coulomb_soc = coulomb_soc * 0.99 + ocv_soc * 0.01

        # ====================== FINALIZE ======================
        self.soc = round(max(0.0, min(100.0, coulomb_soc)), 1)

        # Simple SoH from cycle counting
        cycles = self._calculate_cycles()
        fade_per_cycle = 20.0 / self.cfg.design_cycle_life   # 20% fade over full life
        self.soh = round(max(70.0, 100.0 - cycles * fade_per_cycle), 1)

        self.last_time = now
        self.last_voltage = voltage
        self.last_temp = temperature

        log_soc.info(f"SOC {self.soc}% | SoH {self.soh}% | Cycles {cycles} | η={self.cfg.charge_efficiency:.2f}/{self.cfg.discharge_efficiency:.2f}")
        return self.soc

    def get_status(self):
        if self.relaxed_start_time and time.time() - self.relaxed_start_time >= self.cfg.relaxed_hold_time:
            return "RELAXED"
        return "LOAD"

    def get_ocv(self, voltage, current, temperature):
        return self._estimate_ocv(voltage, current, temperature)

    def reset(self, soc=50.0, soh=100.0):
        self.soc = max(0.0, min(100.0, soc))
        self.soh = max(70.0, min(100.0, soh))
        self.total_throughput_ah = 0.0
        self.last_time = time.time()
        self.relaxed_start_time = None
        self.voltage_history.clear()
        save_state(self)


# =============================================================================
# Recommended usage in main.py
# =============================================================================
"""
soc_cfg = soc_config()
soc_cfg.init_mqtt_entities()          # now includes efficiency & cycle life

soc_estimator = BatterySOC(soc_cfg)

asyncio.create_task(autosave_task(soc_estimator, 300))

# In your main loop:
soc = soc_estimator.update(current, voltage, temperature, battery.info.ncell)
"""