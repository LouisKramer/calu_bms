import asyncio
from machine import WDT, Pin
from common.logger import Logger
from common.common import protection_config, master_data
from common.HAL import master_hal as HAL
from lib.virt_slave import *

class Protector:
    PROT_STAGE_OFF      = 0 # not started
    PROT_STAGE_STABLE   = 1 # inital state for achieving measurement stability
    PROT_STAGE_0        = 2 # no protection activated
    PROT_STAGE_1        = 3 # SiC procection active
    PROT_STAGE_2        = 4 # Stage 1 and external relay acivated.
    
    def __init__(self, cfg: protection_config = None, slaves: Slaves = None, data: master_data = None):
        self.log            = Logger()
        self.wdt            = None
        self.cfg            = cfg or protection_config()
        self.slaves         = slaves
        self.data           = data
        self.stage          = self.PROT_STAGE_OFF
        self.stage_stable_delay = 0
        self.stage_2_delay  = self.cfg.prot_rel_trigger_delay
        self.sic_driver     = Pin(HAL.BAT_FAULT_PIN, Pin.OUT, value=0)
        self.rel_main       = Pin(HAL.INT_REL1_PIN, Pin.OUT, value=0)
        self.rel_pre_charge = Pin(HAL.INT_REL0_PIN, Pin.OUT, value=0)
        self.oc_in          = Pin(HAL.CURRENT_FAULT_PIN, Pin.IN)
        self._last_logged_msg = ""   # prevent log spam
        
    def start(self, slaves: Slaves, data: master_data):
        if self.stage != self.PROT_STAGE_OFF:
            self.log.warn("Protection already started")
            return False

        if slaves is None or data is None:
            self.log.error("Cannot start protector – missing slaves or data object")
            return False

        self.log.info("Starting protection system")
        self.slaves = slaves
        self.data = data

        self.stage_stable_delay = self.cfg.prot_stable_delay_seconds
        self.stage_2_delay = self.cfg.prot_rel_trigger_delay

        self.oc_in.irq(handler = self._oc_trigger, trigger = Pin.IRQ_FALLING)
        self.wdt = WDT(timeout = 8000)
        self.stage = self.PROT_STAGE_STABLE
        asyncio.create_task(self._worker())
        return True

    async def connect_to_inv(self):
        """Safe connection to inverter with pre-charge logic – all thresholds from config"""
        if self.stage != self.PROT_STAGE_0:
            self.log.warn("Protection not ready for connection (stage != 0)")
            return False

        delta = abs(self.data.vinv - self.data.vpack)

        # Pre-charge if inverter voltage is very low
        if self.data.vinv < self.cfg.prot_precharge_vinv_threshold:
            self.log.info(f"DC-Link voltage low (< {self.cfg.prot_precharge_vinv_threshold} V) → starting pre-charge")
            await self._precharge()

        # Large voltage difference → warn / refuse
        elif delta > self.cfg.prot_connect_delta_warn:
            self.log.warn(f"Large voltage delta: vinv={self.data.vinv:.1f}V, vpack={self.data.vpack:.1f}V "
                          f"(warn threshold = {self.cfg.prot_connect_delta_warn} V)")
            if delta > self.cfg.prot_connect_delta_critical:
                self.log.error(f"Voltage difference too large (> {self.cfg.prot_connect_delta_critical} V) – refusing connection")
                return False

        await self._connect_main()
        return True

    async def _connect_main(self):
        self.rel_main.value(1)
        await asyncio.sleep(1)
        self.sic_driver.value(1)
        await asyncio.sleep(1)
    
    async def _precharge(self):
            self.rel_pre_charge.value(1)
            await asyncio.sleep(2)
            self.rel_main.value(1)
            self.rel_pre_charge.value(0)

    def protect(self):
        self.wdt.feed()
        check_message = self._check()

        if self.stage == self.PROT_STAGE_STABLE:
            self.stage_stable_delay -= 1
            if self.stage_stable_delay <= 0:
                self.stage = self.PROT_STAGE_0
                self.log.info("Protection stage STABLE → 0 (normal operation)")

        elif self.stage == self.PROT_STAGE_0:
            if check_message:
                self.trigger_stage_1()
                self.log.warn(check_message)
                self._last_logged_msg = check_message

        elif self.stage == self.PROT_STAGE_1:
            if check_message:
                if check_message != self._last_logged_msg:
                    self.log.warn(check_message)
                    self._last_logged_msg = check_message
                self.stage_2_delay -= 1
                if self.stage_2_delay <= 0:
                    self.trigger_stage_2()
                    self.log.warn("Entering protection stage 2 – main relay opened")
            else:
                # Fault cleared
                self.stage_2_delay = self.cfg.prot_rel_trigger_delay
                self.stage = self.PROT_STAGE_0
                self.log.info("Fault cleared in stage 1 → returning to stage 0")
                self._last_logged_msg = ""

        elif self.stage == self.PROT_STAGE_2:
            if check_message and check_message != self._last_logged_msg:
                self.log.warn(f"Stage 2 active – still detecting: {check_message}")
                self._last_logged_msg = check_message

        else:
            self.log.error(f"Unknown protection stage: {self.stage}")


    def _check(self):
        if self.slaves is None or self.data is None:
            return "Protector not initialized"

        if getattr(self.slaves, 'slave_lost_flag', False):
            return "Slave lost detected!"

        # === Pack level ===
        if not (self.cfg.prot_min_pack_vol <= self.data.vpack <= self.cfg.prot_max_pack_vol):
            return f"Pack voltage {self.data.vpack:.2f}V out of limits!"

        if self.data.tpack > self.cfg.prot_max_temp:
            return f"Pack temp {self.data.tpack:.1f}°C too high!"

        if not (self.cfg.prot_min_current <= self.data.current <= self.cfg.prot_max_current):
            return f"Current {self.data.current:.1f}A out of limits!"

        # === Per-slave checks ===
        invalid_count = 0
        all_cells = []
        all_temps = []
        all_strings = []

        for s in self.slaves:
            # Cell voltages
            for i, vc in enumerate(s.battery.meas.vcell):
                if vc <= 0.5:
                    invalid_count += 1
                else:
                    all_cells.append(vc)
                    if not (self.cfg.prot_min_cell_vol <= vc <= self.cfg.prot_max_cell_vol):
                        return f"Cell {i} on slave {s.battery.info.addr} → {vc:.3f}V out of limits!"

            # Temperatures
            for i, t in enumerate(s.battery.meas.temps):
                if t > 0.0:
                    all_temps.append(t)
                    if t > self.cfg.prot_max_temp:
                        return f"Temp {i} on slave {s.battery.info.addr} → {t:.1f}°C too high!"

            # String voltage
            all_strings.append(s.battery.meas.vstr)
            if not (self.cfg.prot_min_str_vol <= s.battery.meas.vstr <= self.cfg.prot_max_str_vol):
                return f"String voltage slave {s.battery.info.addr} → {s.battery.meas.vstr:.2f}V out of limits!"

        # === Additional global checks ===
        if invalid_count > self.cfg.prot_max_invalid_cells:
            return f"Too many invalid cell readings ({invalid_count})!"

        if len(all_cells) >= 2:
            if max(all_cells) - min(all_cells) > self.cfg.prot_max_cell_delta_vol:
                return f"Cell voltage imbalance: {max(all_cells)-min(all_cells):.3f}V > limit"

        if len(all_temps) >= 2:
            if max(all_temps) - min(all_temps) > self.cfg.prot_max_temp_delta:
                return f"Temperature spread: {max(all_temps)-min(all_temps):.1f}°C > limit"

        if len(all_strings) >=2:
            if max(all_strings) - min(all_strings) > self.cfg.prot_max_str_delta_vol:
                return f"String imbalance: {max(all_cells)-min(all_cells):.3f}V > limit"

        return None
    
    def trigger_stage_1(self):
        self.sic_driver.value(0)
        self.stage = self.PROT_STAGE_1
    
    def trigger_stage_2(self):
        self.rel_main.value(0)
        self.stage = self.PROT_STAGE_2

    def _oc_trigger(self, pin):
        """Hardware over-current – immediate full disconnect"""
        self.log.error("!!! HARDWARE OVER-CURRENT TRIGGERED !!!")
        self.trigger_stage_2()
        pin.irq(handler=None)   # disable further interrupts to prevent flooding

    async def _worker(self):
        while True:
            try:
               self.protect()
            except Exception as e:
                self.log.error(f"Protection worker error: {e} trigger stage 1")
                self.trigger_stage_1()
            await asyncio.sleep(1.0)

    