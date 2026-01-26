import asyncio
from machine import WDT, Pin
from common.logger import Logger
from common.common import protection_config, master_data
from common.HAL import master_hal as HAL
from lib.virt_slave import *

class Protector:
    PROT_STAGE_0 = 0 # no protection activated
    PROT_STAGE_1 = 1 # SiC procection active
    PROT_STAGE_2 = 2 # Stage 1 and external relay acivated.
    def __init__(self, config: protection_config, slaves: Slaves = None, data: master_data = None):
        self.log            = Logger()
        self.wdt            = None
        self.cfg            = config
        self.slaves         = slaves
        self.data           = data
        self.stage          = self.PROT_STAGE_0
        self.stage_2_delay  = config.prot_rel_trigger_delay
        self.sic_driver     = Pin(HAL.BAT_FAULT_PIN, Pin.OUT)
        self.rel_main       = Pin(HAL.INT_REL1_PIN, Pin.OUT)
        self.rel_pre_charge = Pin(HAL.INT_REL0_PIN, Pin.OUT)
        self.oc_in          = Pin(HAL.CURRENT_FAULT_PIN, Pin.IN)
        self._last_logged_msg = ""   # prevent log spam
        
    async def start(self, slaves: Slaves, data: master_data):
        self.slaves = slaves
        self.data = data
        delta = abs(self.data.vinv - self.data.vpack)
        if self.data.vinv < 50 : #TODO: find proper value
            #DC-Link precharge from battery
            await self._precharge()
        elif delta > 80:        #TODO: find proper value
            self.log.warn(f"Large voltage delta detected: vinv={self.data.vinv:.1f} V > vpack={self.data.vpack:.1f} V")
            if delta > 150:     #TODO: find proper value
                self.log.error("Voltage difference too large - risk of high inrush to battery. Waiting or aborting.")
                # Option: wait for sun to drop / load to consume, or refuse connection
                return
        self.rel_main.on()
        await asyncio.sleep(1)
        self.sic_driver.on()
        await asyncio.sleep(1)
        self.oc_in.irq(handler = self._oc_trigger, trigger = Pin.IRQ_FALLING)
        self.wdt = WDT(timeout = 8000)
        asyncio.create_task(self._worker())
    
    async def _precharge(self):
            self.rel_pre_charge.on()
            await asyncio.sleep(2)
            self.rel_main.on()
            self.rel_pre_charge.off()

    def protect(self):
        self.wdt.feed()
        msg = self._check()
        if self.stage == self.PROT_STAGE_0:
            if msg is not None:
                self.trigger_stage_1()
                self.log.warn(msg)
                self._last_logged_msg = msg

        elif self.stage == self.PROT_STAGE_1:
            if msg is not None:
                # Only log if message changed → reduces spam
                if msg != self._last_logged_msg:
                    self.log.warn(msg)
                    self._last_logged_msg = msg
                self.stage_2_delay -= 1
                if self.stage_2_delay <= 0:
                    self.trigger_stage_2()
                    self.log.warn("Entering protection stage 2 - relay opened")
            else:
                # Fault cleared → reset delay counter
                self.stage_2_delay = self.cfg.prot_rel_trigger_delay
                # Optional: log recovery (uncomment if desired)
                # self.log.info("Fault cleared in stage 1 – delay reset")

        elif self.stage == self.PROT_STAGE_2:
            # In many BMS designs: continue monitoring, but no automatic recovery
            if msg is not None and msg != self._last_logged_msg:
                self.log.warn(f"Stage 2 active - still detecting: {msg}")
                self._last_logged_msg = msg

        else:
            self.log.error(f"Unknown protection stage: {self.stage}")


    def _check(self):
        if not(self.cfg.prot_min_pack_vol <= self.data.vpack <= self.cfg.prot_max_pack_vol):
            return f"Battery Pack over/under Voltage {self.data.vpack}V detected!"
        if self.data.tpack >= self.cfg.prot_max_temp:
            return f"Battery Pack over Temperature {self.data.tpack}°C detected!"

        if not(self.cfg.prot_min_current <= self.data.current <= self.cfg.prot_max_current):
            return f"Battery Pack over/under Current {self.data.current}A detected!"

        for s in self.slaves:
            #check cell voltages
            for i, vc in enumerate(s.battery.meas.vcell):
                if not (self.cfg.prot_min_cell_vol <= vc <= self.cfg.prot_max_cell_vol):
                    return f"Cell {i} on slave {s.battery.info.addr} over/under Voltage {vc}V detected!"
            #check string temps
            for i, t in enumerate(s.battery.meas.temps):
                if t > self.cfg.prot_max_temp:
                    return f"Temp {i} on slave {s.battery.info.addr} over Temperature {t}°C detected!"
            #check string voltage
            if not (self.cfg.prot_min_str_vol <= s.battery.meas.vstr <= self.cfg.prot_max_str_vol):
                return f"Slave {s.battery.info.addr} string over/under Voltage {s.battery.meas.vstr}V detected!"
        return None
    
    def trigger_stage_1(self):
        self.sic_driver.off()
        self.stage = self.PROT_STAGE_1
    
    def trigger_stage_2(self):
        self.rel_main.off()
        self.stage = self.PROT_STAGE_2

    # External IRQ trigger
    def _oc_trigger(self, pin):
        self.log.warn(f"External oc trigger!")
        pass

    async def _worker(self):
        while True:
            try:
               self.protect()
            except Exception as e:
                self.log.error(f"Protection worker error: {e} trigger stage 1")
                self.trigger_stage_1()
            await asyncio.sleep(1.0)

    