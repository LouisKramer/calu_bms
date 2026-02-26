# BMSbal.py
import asyncio
import ustruct
import time
from machine import Pin, PWM
from common.logger import Logger
from common.common import battery
from common.HAL import slave_hal as HAL


class BMSbal:
    """
    Passive cell balancer for 32 cells (2×16) using 1–2 PCA9685 chips.
    • Guarantees NO adjacent cells balance at the same time
    • Manual + automatic voltage-based balancing
    • Internal and external balancing are now MUTUALLY EXCLUSIVE
    """

    def __init__(self, pcas: list):
        self.pcas = pcas
        self.log = Logger()

        self._requested = {}          # cell 0..31 → duty (0–4095)
        self._task = None
        self._phase = 0
        self.phase_duration_ms = 250

        # Balancing modes
        self._auto_enabled = False          # internal PCA9685 balancing
        self._external_bal_enabled = False  # external active balancing
        self._batteries = None

        # Auto-balancing config
        self.bal_start_vol = 3.40
        self.bal_threshold = 0.01
        self.bal_max_duty = 0.65
        self.auto_update_interval_ms = 6000

        # External balancing hardware
        self._ext_bal_pin = None
        self._ext_bal_pwm = None

    async def start(self, phase_duration_ms: int = 250):
        if self._task and not self._task.done():
            self._task.cancel()

        self.phase_duration_ms = phase_duration_ms
        self._task = asyncio.create_task(self._main_task(), name="CellBalancer")
        self.log.info(f"CellBalancer started (phase = {phase_duration_ms} ms)")

    async def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None
        await self.clear_all()
        self._auto_enabled = False
        self._external_bal_enabled = False
        self.log.info("CellBalancer stopped")

    # ====================== MANUAL BALANCING ======================
    def set(self, cell: int, duty: float | int):
        if not 0 <= cell <= 31:
            raise ValueError("Cell 0–31 only")
        if isinstance(duty, float):
            duty = int(duty * 4095 + 0.5)
        if duty <= 0:
            self._requested.pop(cell, None)
        else:
            self._requested[cell] = min(duty, 4095)

    def set_many(self, cell_duties: dict[int, float | int]):
        for cell, duty in cell_duties.items():
            self.set(cell, duty)

    # ====================== AUTO BALANCING ======================
    def enable_auto(self, bat: battery, max_duty: float = 0.65):
        """Enable balancing – respects bal_en / bal_ext_en from config"""
        if not bat:
            raise ValueError("No battery object provided")

        self._batteries = bat

        self.bal_start_vol = bat.conf.bal_start_vol
        self.bal_threshold = bat.conf.bal_threshold
        self.bal_max_duty = max_duty

        self._external_bal_enabled = bat.conf.bal_ext_en
        self._auto_enabled = bat.conf.bal_en and not bat.conf.bal_ext_en   # ← MUTUAL EXCLUSION

        # Setup external hardware only if external balancing is selected
        if self._external_bal_enabled:
            self._ext_bal_pin = Pin(HAL.ACT_BAL_PIN, Pin.OUT, value=0)
            self._ext_bal_pwm = PWM(Pin(HAL.ACT_BAL_PWM_PIN), freq=1000, duty=0)
            self.log.info("🔌 External active balancing ENABLED (internal disabled)")

        if self._auto_enabled:
            self.log.info(f"Internal auto balancing ENABLED | start@{self.bal_start_vol}V | "
                          f"threshold={self.bal_threshold}V | max_duty={max_duty*100:.0f}%")
        elif not self._external_bal_enabled:
            self.log.warn("Neither internal nor external balancing is enabled in config")

    def disable_auto(self):
        self._auto_enabled = False
        self._external_bal_enabled = False
        if self._ext_bal_pin:
            self._ext_bal_pin.value(0)
            if self._ext_bal_pwm:
                self._ext_bal_pwm.duty(0)
        self.log.info("🔌 All balancing disabled")

    # ====================== BACKGROUND TASK ======================
    async def _main_task(self):
        last_auto = 0
        while True:
            try:
                now = time.ticks_ms()

                if (self._auto_enabled and self._batteries and
                        time.ticks_diff(now, last_auto) > self.auto_update_interval_ms):
                    self._update_auto_balancing()
                    last_auto = now

                await self._apply_phase()
                await asyncio.sleep_ms(self.phase_duration_ms)
                self._phase = 1 - self._phase

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Balancer task error: {e}")
                await asyncio.sleep_ms(2000)

    def _update_auto_balancing(self):
        all_vcell = self._batteries.meas.vcell
        valid = [v for v in all_vcell if v > 0.5]
        if not valid:
            return

        max_v = max(valid)
        new_requested = {}

        for cell in range(32):
            v = all_vcell[cell]
            if v <= 0.5:
                continue
            if v >= self.bal_start_vol and (max_v - v) <= self.bal_threshold:
                delta = max_v - v
                duty = int(self.bal_max_duty * 4095 * (1.0 - delta / 0.05))
                duty = max(200, min(duty, int(self.bal_max_duty * 4095)))
                new_requested[cell] = duty

        self._requested = new_requested

        active = len(new_requested)
        if active > 0:
            self.log.info(f"Auto-balancing {active} top cells (max={max_v:.3f}V)")

        # External signal (only when external mode is active)
        if self._external_bal_enabled and self._ext_bal_pin:
            active_ext = 1 if active > 0 else 0
            self._ext_bal_pin.value(active_ext)
            if self._ext_bal_pwm:
                self._ext_bal_pwm.duty(512 if active_ext else 0)   # 50% PWM when active

    async def _apply_phase(self):
        """Only run internal PCA9685 balancing when internal mode is enabled"""
        if not self._auto_enabled:
            return   # external mode → skip internal

        for pca_idx, pca in enumerate(self.pcas):
            base = pca_idx * 16
            data = bytearray(64)

            for ch in range(16):
                cell = base + ch
                duty = self._requested.get(cell, 0)

                if (cell % 2) != self._phase:
                    duty = 0

                if duty == 0:
                    on_off = b'\x00\x00\x00\x10'
                elif duty >= 4095:
                    on_off = b'\x00\x10\x00\x00'
                else:
                    on_off = ustruct.pack('<HH', 0, duty)

                data[ch*4:(ch+1)*4] = on_off

            pca.i2c.writeto_mem(pca.address, 0x06, data)

    async def clear_all(self):
        self._requested.clear()
        for pca in self.pcas:
            pca.all_duty(0)
        if self._ext_bal_pin:
            self._ext_bal_pin.value(0)
            if self._ext_bal_pwm:
                self._ext_bal_pwm.duty(0)
        self.log.info("All balancing cleared")