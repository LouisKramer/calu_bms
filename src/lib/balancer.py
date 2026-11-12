# balancer.py - Passive cell balancing via PCA9685 -> PhotoMOS -> bleed resistor
import asyncio
import time
from lib.PCA9685 import PCA9685

CELL_V_MAX = 3.65   # worst-case cell voltage used for the resistor power estimate


class Balancer:
    """
    Physical cell n (1..32) is PCA9685 #((n-1)//16), channel (n-1)%16.
    All outputs are forced off at start-up. Any active command expires after
    `timeout_s` unless refreshed, so a hung control loop cannot keep bleeding cells.
    """

    def __init__(self, i2c, addrs, allowed_cells, max_duty=38, pwm_freq=100,
                 resistor_ohm=5.1, resistor_rated_w=1.0, timeout_s=30, log=None):
        self.log = log
        self.allowed = set(allowed_cells)
        self.resistor_ohm = resistor_ohm
        self.resistor_rated_w = resistor_rated_w
        self.timeout_ms = int(timeout_s * 1000)
        nr_pca = 2 if any(c > 16 for c in self.allowed) else 1
        self.pcas = []
        for a in addrs[:nr_pca]:
            p = PCA9685(i2c, address=a)
            p.set_pwm_freq(pwm_freq)
            p.all_off()
            self.pcas.append(p)
        self.max_duty = 0
        self.set_max_duty(max_duty)
        self._active = {}            # cell -> duty
        self._paused = False
        self._last_cmd = time.ticks_ms()

    # ------------------------------------------------------------------
    @property
    def cooling_threshold(self):
        """Duty (%) above which a bleed resistor exceeds its rated power."""
        p_full = CELL_V_MAX * CELL_V_MAX / self.resistor_ohm
        return min(100, int(100 * self.resistor_rated_w / p_full))

    def resistor_power(self, duty):
        return CELL_V_MAX * CELL_V_MAX / self.resistor_ohm * duty / 100

    def set_max_duty(self, duty):
        if not 0 <= duty <= 100:
            raise ValueError("max duty must be 0..100 %")
        self.max_duty = duty
        if duty > self.cooling_threshold:
            self._warn(
                f"Balancing max duty {duty}% -> ~{self.resistor_power(duty):.1f} W per resistor "
                f"(rated {self.resistor_rated_w} W, limit {self.cooling_threshold}%): "
                "bleed resistors need passive cooling (heatsink/airflow)!")

    # ------------------------------------------------------------------
    def _warn(self, msg):
        if self.log:
            self.log.warn(msg, ctx="balancer")
        else:
            print("[W] balancer |", msg)

    def _write(self, cell, duty):
        pca = self.pcas[(cell - 1) // 16]
        pca.set_duty((cell - 1) % 16, duty)

    def apply(self, cells, duty=None):
        """
        Balance exactly the given physical cells (others off).
        duty defaults to max_duty and is clamped to it.
        """
        duty = self.max_duty if duty is None else min(duty, self.max_duty)
        wanted = {}
        for c in cells:
            if c not in self.allowed:
                raise ValueError(f"cell {c} not configured for balancing")
            if duty > 0:
                wanted[c] = duty
        if not self._paused:
            for c in self._active:
                if c not in wanted:
                    self._write(c, 0)
            for c, d in wanted.items():
                if self._active.get(c) != d:
                    self._write(c, d)
        self._active = wanted
        self._last_cmd = time.ticks_ms()

    def all_off(self):
        for p in self.pcas:
            p.all_off()
        self._active = {}

    @property
    def active_cells(self):
        return sorted(self._active)

    # ------------------------------------------------------------------
    # Measurement window: tap wires carry bleed current, which falsifies readings
    # ------------------------------------------------------------------
    def pause(self):
        if not self._paused:
            for p in self.pcas:
                p.all_off()
            self._paused = True

    def resume(self):
        if self._paused:
            self._paused = False
            for c, d in self._active.items():
                self._write(c, d)

    # ------------------------------------------------------------------
    async def watchdog_task(self, period_s=1):
        while True:
            if self._active and time.ticks_diff(time.ticks_ms(), self._last_cmd) > self.timeout_ms:
                self._warn("No balancing command within timeout -> all off")
                self.all_off()
            await asyncio.sleep(period_s)
