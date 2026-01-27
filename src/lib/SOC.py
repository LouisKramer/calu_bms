import asyncio
import time
import json
import os
from collections import deque
from common.logger import *
from common.common import *

log_soc = Logger()
# =============================================================================
# Persistence Functions
# =============================================================================

def save_state(estimator, path="soc_state.json"):
    """
    Save the current SOC estimator state to non-volatile storage.

    This function serializes critical runtime state to a JSON file on the
    MicroPython filesystem (typically flash). The state survives power cycles
    and is automatically restored on boot.

    Args:
        estimator (BatterySOC): The SOC estimator instance to save.
        path (str): File path for state storage. Defaults to "soc_state.json".

    Raises:
        OSError: If write fails (e.g. full flash, read-only FS).
        Exception: Any other error during serialization.

    Example:
        >>> save_state(soc_estimator)
        # Creates soc_state.json with SOC, timestamps, history
    """
    try:
        log_soc.info("Saving SOC state to non-volatile storage")
        state = {
            "soc": estimator.soc,
            "last_time": estimator.last_time,
            "relaxed_start_time": estimator.relaxed_start_time,
            "voltage_history": list(estimator.voltage_history),
            "last_voltage": estimator.last_voltage,
            "last_temp": estimator.last_temp
        }
        with open(path, "w") as f:
            f.write(json.dumps(state))
    except Exception as e:
        log_soc.error(f"Failed to save SOC state: {e}")


def load_state(estimator, path="soc_state.json"):
    """
    Load previously saved SOC state from non-volatile storage.

    Restores SOC, timing, and history from a JSON file. If the file is missing
    or corrupted, the estimator falls back to initial configuration values.

    Args:
        estimator (BatterySOC): The SOC estimator instance to restore into.
        path (str): File path to load from. Defaults to "soc_state.json".

    Returns:
        bool: True if state was loaded successfully, False otherwise.

    Example:
        >>> loaded = load_state(soc_estimator)
        >>> print("Recovered SOC:", soc_estimator.soc)
    """
    if path not in os.listdir():
        return False
    try:
        log_soc.info("Loading SOC state from non-volatile storage")
        with open(path, "r") as f:
            state = json.loads(f.read())
        estimator.soc = max(0.0, min(100.0, state.get("soc", estimator.soc)))
        estimator.last_time = state.get("last_time", time.time())
        estimator.relaxed_start_time = state.get("relaxed_start_time")
        estimator.voltage_history = deque(state.get("voltage_history", [])[-10:], 10)
        estimator.last_voltage = state.get("last_voltage")
        estimator.last_temp = state.get("last_temp")
        log_soc.info(f"SOC state loaded successfully: SOC={estimator.soc}%")
        return True
    except Exception as e:
        log_soc.error(f"Failed to load SOC state: {e}")

        return False


# =============================================================================
# Auto-Save Task
# =============================================================================

async def autosave_task(estimator, interval=300):
    """
    Background task that periodically saves SOC state.

    Runs indefinitely, saving the estimator state every `interval` seconds.
    Should be launched once at startup using `asyncio.create_task()`.

    Args:
        estimator (BatterySOC): The estimator to save.
        interval (int): Save interval in seconds. Default: 300 (5 minutes).

    Example:
        >>> asyncio.create_task(autosave_task(soc_estimator, 300))
    """
    while True:
        await asyncio.sleep(interval)
        save_state(estimator)


# =============================================================================
# BatterySOC Class
# =============================================================================

class BatterySOC:
    """
    Hybrid State-of-Charge (SOC) estimator for series-connected battery packs.

    Combines:
      - Coulomb counting (integrates current over time)
      - OCV-based correction using voltage lookup table
      - Temperature-compensated internal resistance
      - Relaxed-state recalibration
      - Non-volatile state persistence

    Designed for MicroPython on resource-constrained devices (ESP32, RP2040, etc.).
    All operations are async-friendly and use minimal RAM.

    Configuration is passed as a dictionary at initialization.
    """

    def __init__(self):
        """
        Initialize the SOC estimator with battery and algorithm parameters.

        Args:
            config (dict): Configuration dictionary. Required keys:
                - 'capacity_ah': Battery capacity in Amp-hours
                - 'num_cells': Number of cells in series
                - 'cell_ir': Cell internal resistance in Ohms (at ref temp)
                Optional keys:
                - 'initial_soc': Starting SOC (%) [default: 50.0]
                - 'initial_temp': Starting temperature (°C) [default: 25.0]
                - 'ir_ref_temp': Reference temperature for IR (°C) [default: 25.0]
                - 'ir_temp_coeff': IR temp coefficient (%/°C) [default: 0.004]
                - 'current_threshold': Current below which battery is "relaxed" (A)
                - 'voltage_stable_threshold': Max voltage change for stability (V)
                - 'relaxed_hold_time': Time to confirm relaxed state (s)
                - 'per_cell_voltage_soc_table': Custom voltage-SOC curve

        Raises:
            ValueError: If num_cells or capacity_ah are invalid.

        Example:
            >>> config = {
            ...     'capacity_ah': 100.0,
            ...     'num_cells': 4,
            ...     'cell_ir': 0.040,
            ...     'initial_soc': 80.0
            ... }
            >>> estimator = BatterySOC(config)
        """
        self.config = soc_config()
        # --- Voltage-SOC Lookup Table ---
        self.default_per_cell = [
            (3.60, 100.0),  # 100% - Full charge
            (3.40,  95.0),
            (3.35,  80.0),
            (3.325, 60.0),
            (3.30,  40.0),
            (3.275, 20.0),
            (3.20,  10.0),
            (2.50,   0.0)   # 0% - Deep discharge
        ]
        self.num_cells = 0
        # --- Runtime State ---
        self.soc = float(self.config.initial_soc)
        self.last_time = time.time()
        self.last_voltage = None
        self.last_temp = 25.0
        self.relaxed_start_time = None
        self.voltage_history = deque([],10)

        # Load persisted state
        if not load_state(self, "soc_state.json"):
            log_soc.info("No saved SOC state found; starting from initial configuration")

    # -------------------------------------------------------------------------
    # Internal Helper Methods
    # -------------------------------------------------------------------------

    def _get_compensated_ir(self, temp):
        """
        Calculate temperature-compensated internal resistance.

        Uses linear model: R(T) = R_ref * (1 + α * (T - T_ref))

        Args:
            temp (float): Current battery temperature in °C.

        Returns:
            float: Temperature-compensated pack resistance in Ohms.
        """
        delta_t = temp - self.config.ir_ref_temp
        factor = 1.0 + (self.config.ir_temp_coeff * delta_t)
        return self.config.cell_ir * self.num_cells * factor

    def _interpolate_soc(self, voltage):
        """
        Linear interpolation in pack-level voltage-SOC lookup table.

        Args:
            voltage (float): Estimated OCV in Volts.

        Returns:
            float: Corresponding SOC in percent (0.0 to 100.0).
        """
        table = self.pack_table
        if voltage >= table[0][0]: return 100.0
        if voltage <= table[-1][0]: return 0.0
        for i in range(len(table) - 1):
            v1, soc1 = table[i]
            v2, soc2 = table[i + 1]
            if v2 <= voltage <= v1:
                return soc1 + (soc2 - soc1) * (voltage - v1) / (v2 - v1)
        return 0.0

    def _estimate_ocv(self, voltage, current, temp):
        """
        Estimate Open Circuit Voltage using temperature-compensated IR.

        OCV = V_measured + I * R_internal(T)

        Args:
            voltage (float): Measured pack voltage (V)
            current (float): Pack current (+ = charge, - = discharge) (A)
            temp (float): Battery temperature (°C)

        Returns:
            float: Estimated OCV in Volts.
        """
        ir = self._get_compensated_ir(temp)
        return voltage + (current * ir)

    def _is_voltage_stable(self):
        """
        Check if voltage has been stable over recent samples.

        Stability = max - min < threshold over last 5+ samples.

        Returns:
            bool: True if voltage is stable.
        """
        if len(self.voltage_history) < 5:
            return False
        return max(self.voltage_history) - min(self.voltage_history) < self.config.voltage_stable_threshold

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def update(self, current, voltage, temperature, nr_cells):
        """
        Update SOC estimate with new sensor readings.

        Main entry point. Call once per sampling interval.

        Args:
            current (float): Battery current in Amps (+ = charging)
            voltage (float): Pack voltage in Volts
            temperature (float): Battery temperature in °C

        Returns:
            float: Updated SOC in percent (0.0 - 100.0)

        Example:
            >>> soc = await estimator.update(-15.5, 12.8, 22.0)
        """
        now = time.time()
        dt = now - self.last_time if self.last_time else 0.1
        self.num_cells = nr_cells
        self.pack_table = [(v * self.num_cells, soc) for v, soc in self.default_per_cell]
        # === Coulomb Counting ===
        ah_delta = (current * dt) / 3600.0
        coulomb_soc = self.soc - (ah_delta / self.config.capacity_ah) * 100.0
        coulomb_soc = max(0.0, min(100.0, coulomb_soc))

        # === OCV Estimation ===
        ocv = self._estimate_ocv(voltage, current, temperature)
        self.voltage_history.append(voltage)

        # === Relaxed State Detection ===
        low_i = abs(current) < self.config.current_threshold
        stable = self._is_voltage_stable()

        if low_i and stable:
            if self.relaxed_start_time is None:
                self.relaxed_start_time = now
            elif now - self.relaxed_start_time >= self.config.relaxed_hold_time:
                ocv_soc = self._interpolate_soc(ocv)
                coulomb_soc += (ocv_soc - coulomb_soc) * 0.2
        else:
            self.relaxed_start_time = None
            ocv_soc = self._interpolate_soc(ocv)
            coulomb_soc += (ocv_soc - coulomb_soc) * 0.001

        # === Finalize ===
        self.soc = round(max(0.0, min(100.0, coulomb_soc)),1)
        self.last_time = now
        self.last_voltage = voltage
        self.last_temp = temperature
        log_soc.info(f"Updated SOC: {self.soc}%")
        return self.soc

    def get_status(self):
        """
        Get current battery operational status.

        Returns:
            str: "RELAXED" if low current and stable for hold time, else "LOAD".
        """
        if (self.relaxed_start_time and
            time.time() - self.relaxed_start_time >= self.config.relaxed_hold_time):
            return "RELAXED"
        return "LOAD"

    def get_ocv(self, voltage, current, temperature):
        """
        Convenience method to estimate OCV without full update.

        Args:
            voltage, current, temperature: Latest sensor values.

        Returns:
            float: Estimated OCV in Volts.
        """
        return self._estimate_ocv(voltage, current, temperature)

    def reset(self, soc=50.0):
        """
        Reset SOC estimator to a known state and save.

        Args:
            soc (float): New SOC value in percent.
        """
        self.soc = max(0.0, min(100.0, soc))
        self.last_time = time.time()
        self.relaxed_start_time = None
        self.voltage_history.clear()
        save_state(self)


# =============================================================================
# Example Usage (main.py)
# =============================================================================

"""
# main.py
import asyncio
from battery_soc import BatterySOC, autosave_task

# Replace with your actual sensor drivers
# cur.read_current(samples=10) -> float
# vol.read_voltage(channel=0) -> float
# tmp.get_temperature() -> float

config = {
    'capacity_ah': 100.0,
    'num_cells': 4,
    'initial_soc': 80.0,
    'cell_ir': 0.040,           # 40 mΩ at 25°C
    'ir_ref_temp': 25.0,
    'ir_temp_coeff': 0.004,        # 0.4%/°C
    'current_threshold': 1.0,
    'voltage_stable_threshold': 0.01,
    'relaxed_hold_time': 30.0,
    'sampling_interval': 1.0
}

soc_estimator = BatterySOC(config)

async def main():
    # Auto-save every 5 minutes
    asyncio.create_task(autosave_task(soc_estimator, 300))

    while True:
        current = cur.read_current(samples=10)
        voltage = await vol.read_voltage(channel=0)
        temp = tmp.get_temperature()

        soc = await soc_estimator.update(current, voltage, temp)
        ocv = soc_estimator.get_ocv(voltage, current, temp)
        status = soc_estimator.get_status()
        ir_used = soc_estimator._get_compensated_ir(temp)

        print("SOC: {:.1f}% | V: {:.2f}V | OCV: {:.2f}V | T: {:.1f}°C | "
              "I: {:+.2f}A | IR: {:.1f}mΩ | {}".format(
            soc, voltage, ocv, temp, current, ir_used*1000, status
        ))

        await asyncio.sleep(config['sampling_interval'])

asyncio.run(main())
"""