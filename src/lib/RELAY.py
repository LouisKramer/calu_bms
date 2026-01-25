# relay.py
# MicroPython library for controlling a relay module on ESP32
# Supports configurable GPIO pin and active-high/active-low relays
# Includes a built-in test routine

from machine import Pin
import time
from common.logger import *

log_rel = Logger()

class Relay:
    """
    A class to control a relay module connected to an ESP32 GPIO pin.
    
    Args:
        pin (int): The GPIO pin number connected to the relay module.
        active_high (bool): True if relay activates on HIGH (default), 
                            False if relay activates on LOW.
    
    Example:
        from relay import Relay
        relay = Relay(pin=18, active_high=False)  # Common for many cheap modules
        relay.on()
        relay.test()  # Run the test routine
    """

    def __init__(self, pin: int, active_high: bool = True):
        self._pin = Pin(pin, Pin.OUT, pull=Pin.PULL_DOWN)
        self._active_high = active_high
        self.off()  # Start in safe (off) state

    def on(self):
        """Turn the relay on"""
        log_rel.info("Turning relay ON")
        if self._active_high:
            self._pin.value(1)
        else:
            self._pin.value(0)

    def off(self):
        """Turn the relay off"""
        log_rel.info("Turning relay OFF")
        if self._active_high:
            self._pin.value(0)
        else:
            self._pin.value(1)

    def toggle(self):
        """Toggle the current relay state."""
        log_rel.info("Toggling relay state")
        self._pin.value(not self._pin.value())

    def state(self) -> bool:
        """Return True if relay is currently ON."""
        value = self._pin.value()
        return value == 1 if self._active_high else value == 0

    def test(self, cycles: int = 5, on_time: float = 0.5, off_time: float = 0.5):
        """
        Run a simple test routine: blink the relay several times.
        
        Args:
            cycles (int): Number of on/off cycles (default: 5)
            on_time (float): Time in seconds the relay stays ON
            off_time (float): Time in seconds the relay stays OFF
        """
        log_rel.info("Starting relay test routine...")
        log_rel.info(f"Pin: GPIO{self._pin}, Active {'HIGH' if self._active_high else 'LOW'}")
        log_rel.info(f"Performing {cycles} cycles (ON {on_time}s / OFF {off_time}s)\n")
        for i in range(cycles):
                self.on()
                time.sleep(on_time)
                self.off()
                time.sleep(off_time)
        self.off()  # Ensure relay is off when test ends
        log_rel.info("Relay test completed successfully!")
