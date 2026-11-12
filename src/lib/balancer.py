# balancer.py - Passive cell balancing via PCA9685 -> PhotoMOS -> bleed resistor
import asyncio
import time
from lib.PCA9685 import PCA9685

CELL_V_MAX = 3.65   # worst-case cell voltage for the resistor power estimate


class Balancer:
    """
    Physical cell n (1..32) is PCA9685 #((n-1)//16), channel (n-1)%16.

    Every PCA9685 on the board is forced off at start-up, including one whose cells are
    not configured: it keeps its outputs across an ESP32 reset. An active command expires
    after `timeout_s` unless refreshed by apply(), so a hung control loop cannot keep
    bleeding cells (a crashed interpreter needs the hardware WDT on top of this).
    """

    def __init__(self, i2c, addrs, allowed_cells, max_duty=38, pwm_freq=100,
                 resistor_ohm=5.1, resistor_rated_w=1.0, timeout_s=30, warn=None):
        self._warn = warn or (lambda msg: print("[W] balancer |", msg))
        self.allowed = set(allowed_cells)
        self.resistor_ohm = resistor_ohm
        self.resistor_rated_w = resistor_rated_w
        self.timeout_ms = int(timeout_s * 1000)
        self.pcas = []
        for i, a in enumerate(addrs):
            needed = any((c - 1) // 16 == i for c in self.allowed)
            try:
                self.pcas.append(PCA9685(i2c, address=a, freq=pwm_freq))
            except OSError:
                if needed:
                    raise OSError(f"PCA9685 0x{a:02x} for configured cells not responding")
                self._warn(f"PCA9685 0x{a:02x} not responding (no configured cells)")
                self.pcas.append(None)
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
                f"max duty {duty}% -> ~{self.resistor_power(duty):.1f} W per resistor "
                f"(rated {self.resistor_rated_w} W, limit {self.cooling_threshold}%): "
                "bleed resistors need passive cooling (heatsink/airflow)!")

    # ------------------------------------------------------------------
    def _write(self, cell, duty):
        self.pcas[(cell - 1) // 16].set_duty((cell - 1) % 16, duty)

    def _all_pcas_off(self):
        for p in self.pcas:
            if p:
                p.all_off()

    def apply(self, cells, duty=None):
        """
        Balance exactly the given physical cells (all others off) and refresh the timeout.
        duty defaults to max_duty and is clamped to it.
        """
        duty = self.max_duty if duty is None else min(duty, self.max_duty)
        for c in cells:
            if c not in self.allowed:
                raise ValueError(f"cell {c} not configured for balancing")
        wanted = {c: duty for c in cells} if duty > 0 else {}
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
        self._all_pcas_off()
        self._active = {}

    @property
    def active_cells(self):
        return sorted(self._active)

    # ------------------------------------------------------------------
    # Measurement window: bleed current flows through the tap wires and falsifies readings
    # ------------------------------------------------------------------
    def pause(self):
        if not self._paused:
            self._all_pcas_off()
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
                self._warn("no balancing command within timeout -> all off")
                self.all_off()
            await asyncio.sleep(period_s)
