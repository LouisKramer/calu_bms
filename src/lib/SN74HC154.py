# SN74HC154.py - 4-to-16 line decoder used as SPI chip-select demultiplexer
from machine import Pin


class SN74HC154:
    """
    Address pins A..D select output Y0..Y15, the enable pin drives G1 (active low, G2 tied low).
    The address is only changed while the decoder is disabled, so no other output glitches low.
    """

    def __init__(self, enable_pin, a0_pin, a1_pin, a2_pin, a3_pin):
        self.en = Pin(enable_pin, Pin.OUT, value=1)
        self.addr = [Pin(p, Pin.OUT, value=0) for p in (a0_pin, a1_pin, a2_pin, a3_pin)]
        self._current = 0

    def select(self, output):
        if not 0 <= output <= 15:
            raise ValueError("output must be 0..15")
        self.en(1)
        if output != self._current:
            for i, pin in enumerate(self.addr):
                pin((output >> i) & 1)
            self._current = output
        self.en(0)

    def deselect(self):
        self.en(1)
