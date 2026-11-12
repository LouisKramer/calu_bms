# ADS1118.py - 16-bit ADC driver (single-shot, SPI mode 1)
import asyncio
from machine import Pin

# MUX codes
MUX_AIN0_AIN1 = 0b000
MUX_AIN0_AIN3 = 0b001
MUX_AIN1_AIN3 = 0b010
MUX_AIN2_AIN3 = 0b011
MUX_SE = (0b100, 0b101, 0b110, 0b111)   # AIN0..AIN3 vs GND

FSR = (6.144, 4.096, 2.048, 1.024, 0.512, 0.256, 0.256, 0.256)
DR_SPS = (8, 16, 32, 64, 128, 250, 475, 860)


class ADS1118:
    """
    Chip select either through a demultiplexer (object with select(n)/deselect())
    or a direct GPIO. The SPI bus must be configured for mode 1 (polarity=0, phase=1).

    Conversion data is always two's complement. In single-ended mode only the
    positive half is used, so 1 LSB = FSR / 32768 in every input configuration.
    """

    def __init__(self, spi, demux=None, demux_output=None, cs_pin=None, pga=2, dr=4):
        if (demux is None) == (cs_pin is None):
            raise ValueError("provide either demux + demux_output or cs_pin")
        if demux is not None and not 0 <= demux_output <= 15:
            raise ValueError("demux_output must be 0..15")
        if not 0 <= pga <= 7 or not 0 <= dr <= 7:
            raise ValueError("pga and dr must be 0..7")
        self.spi = spi
        self.demux = demux
        self.demux_output = demux_output
        self.cs = Pin(cs_pin, Pin.OUT, value=1) if cs_pin is not None else None
        self.pga = pga
        self.dr = dr
        self._tx2 = bytearray(2)
        self._rx2 = bytearray(2)

    # ------------------------------------------------------------------
    # Low level
    # ------------------------------------------------------------------
    @property
    def lsb(self):
        return FSR[self.pga] / 32768

    @property
    def conversion_ms(self):
        """Conversion time incl. 20 % margin for the internal oscillator tolerance."""
        return int(1200 / DR_SPS[self.dr]) + 1

    def _config(self, start, mux, ts=0):
        return ((start << 15) | (mux << 12) | (self.pga << 9) | (1 << 8)  # single-shot
                | (self.dr << 5) | (ts << 4) | (1 << 3)                    # DOUT pull-up
                | (0b01 << 1) | 1)                                         # NOP=01 (valid)

    def _xfer(self, tx, rx):
        if self.demux is not None:
            self.demux.select(self.demux_output)
        else:
            self.cs(0)
        try:
            self.spi.write_readinto(tx, rx)
        finally:
            if self.demux is not None:
                self.demux.deselect()
            else:
                self.cs(1)

    def transfer(self, mux, start=True, ts=0):
        """
        Write the config register (optionally starting a conversion) and return
        the signed result of the previous conversion of this device.
        """
        cfg = self._config(1 if start else 0, mux, ts)
        self._tx2[0] = cfg >> 8
        self._tx2[1] = cfg & 0xFF
        self._xfer(self._tx2, self._rx2)
        raw = (self._rx2[0] << 8) | self._rx2[1]
        return raw - 0x10000 if raw & 0x8000 else raw

    def probe(self):
        """
        32-bit cycle: the device echoes its config register in the second word.
        Returns (present, echo). Does not start a conversion.
        """
        cfg = self._config(0, MUX_SE[0])
        tx = bytearray((cfg >> 8, cfg & 0xFF, cfg >> 8, cfg & 0xFF))
        rx = bytearray(4)
        self._xfer(tx, rx)
        echo = (rx[2] << 8) | rx[3]
        # Compare MUX, PGA, MODE, DR and TS_MODE (bits 14..4)
        return (echo & 0x7FF0) == (cfg & 0x7FF0), echo

    # ------------------------------------------------------------------
    # Convenience (one conversion at a time)
    # ------------------------------------------------------------------
    async def read_raw(self, mux):
        self.transfer(mux, start=True)
        await asyncio.sleep_ms(self.conversion_ms)
        return self.transfer(mux, start=False)

    async def read_voltage(self, mux):
        return await self.read_raw(mux) * self.lsb

    async def read_temperature(self):
        """Internal die temperature in degC (14-bit left aligned, 0.03125 degC/LSB)."""
        self.transfer(0, start=True, ts=1)
        await asyncio.sleep_ms(self.conversion_ms)
        return (self.transfer(0, start=False, ts=1) >> 2) * 0.03125
