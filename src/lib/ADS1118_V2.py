# ads1118.py - Full async MicroPython driver for TI ADS1118
# Features:
# • External SPI (hardware)
# • Optional CS pin
# • Single-shot reads (any MUX/PGA/DR)
# • Single-channel continuous mode
# • **Multi-channel continuous round-robin scan** (new!)
# • Temperature sensor
# • Zero blocking sleeps – everything is awaitable

import asyncio
from machine import Pin

class ADS1118:
    # ==================== CONSTANTS ====================
    # Input multiplexer (bits 14-12)
    MUX_AIN0_AIN1 = 0b000   # default differential
    MUX_AIN0_AIN3 = 0b001
    MUX_AIN1_AIN3 = 0b010
    MUX_AIN2_AIN3 = 0b011
    MUX_AIN0_GND  = 0b100   # single-ended
    MUX_AIN1_GND  = 0b101
    MUX_AIN2_GND  = 0b110
    MUX_AIN3_GND  = 0b111

    # PGA (bits 11-9) → Full Scale Range
    PGA_6_144V = 0b000
    PGA_4_096V = 0b001
    PGA_2_048V = 0b010   # default
    PGA_1_024V = 0b011
    PGA_0_512V = 0b100
    PGA_0_256V = 0b101

    # Data rate (bits 7-5)
    DR_8SPS   = 0b000
    DR_16SPS  = 0b001
    DR_32SPS  = 0b010
    DR_64SPS  = 0b011
    DR_128SPS = 0b100   # default
    DR_250SPS = 0b101
    DR_475SPS = 0b110
    DR_860SPS = 0b111

    # Conversion delays (ms) with margin
    _DELAY_MS = [135, 75, 45, 25, 14, 9, 6, 4]
    _FSR      = [6.144, 4.096, 2.048, 1.024, 0.512, 0.256]

    def __init__(self, spi, cs_pin=None):
        self.spi = spi
        if isinstance(cs_pin, (int, str)):
            self.cs = Pin(cs_pin, Pin.OUT, value=1)
        elif isinstance(cs_pin, Pin):
            self.cs = cs_pin
            self.cs.value(1)
        else:
            self.cs = None

        self._mode = None           # None / 'single_cont' / 'multi_scan'
        self._last_pga = None
        self._last_dr = None
        self._scan_mux_list = None
        self._scan_idx = 0

    def _select(self):
        if self.cs:
            self.cs.value(0)

    def _deselect(self):
        if self.cs:
            self.cs.value(1)

    async def _write_config(self, config):
        self._select()
        self.spi.write(config.to_bytes(2, 'big'))
        self._deselect()

    async def _read_raw(self):
        self._select()
        rx = bytearray(2)
        self.spi.write_readinto(b'\x00\x00', rx)
        self._deselect()
        return int.from_bytes(rx, 'big', signed=True)

    # ====================== SINGLE-SHOT ======================
    async def read(self, mux=MUX_AIN0_AIN1, pga=None, data_rate=None, gain = 1.0):
        """One single conversion (flexible)"""
        if pga is None: pga = self.PGA_2_048V
        if data_rate is None: data_rate = self.DR_128SPS

        config = (1 << 15) | (mux << 12) | (pga << 9) | (1 << 8) | (data_rate << 5)
        config |= (1 << 3) | (0b01 << 1) | 1

        await self._write_config(config)
        await asyncio.sleep_ms(self._DELAY_MS[data_rate])

        raw = await self._read_raw()
        fsr = self._FSR[pga]
        voltage = raw * (fsr / 32768.0)
        voltage = round(voltage * gain, 4)
        return voltage

    # ====================== SINGLE-CHANNEL CONTINUOUS ======================
    async def start_continuous(self, mux=MUX_AIN0_AIN1, pga=None, data_rate=None):
        """Start continuous conversion on ONE channel"""
        if pga is None: pga = self.PGA_2_048V
        if data_rate is None: data_rate = self.DR_128SPS

        config = (1 << 15) | (mux << 12) | (pga << 9) | (0 << 8) | (data_rate << 5)
        config |= (1 << 3) | (0b01 << 1) | 1

        await self._write_config(config)
        await asyncio.sleep_ms(self._DELAY_MS[data_rate])

        self._mode = 'single_cont'
        self._last_pga = pga
        self._last_dr = data_rate

    async def read_continuous(self, gain = 1.0):
        """Read latest value (fast, no waiting)"""
        if self._mode != 'single_cont':
            raise RuntimeError("Call start_continuous() first")
        raw = await self._read_raw()
        fsr = self._FSR[self._last_pga]
        voltage = raw * (fsr / 32768.0)
        voltage = round(voltage * gain, 4)
        return voltage

    # ====================== MULTI-CHANNEL CONTINUOUS (NEW!) ======================
    async def start_continuous_scan(self, mux_list, pga=None, data_rate=None):
        """Start round-robin continuous scanning of multiple channels
        mux_list = [MUX_AIN0_GND, MUX_AIN1_GND, ...]"""
        if not mux_list or not isinstance(mux_list, (list, tuple)):
            raise ValueError("mux_list must be a non-empty list of MUX constants")

        if pga is None: pga = self.PGA_2_048V
        if data_rate is None: data_rate = self.DR_128SPS

        self._scan_mux_list = list(mux_list)
        self._scan_idx = 0
        self._last_pga = pga
        self._last_dr = data_rate

        # Start first channel in continuous mode
        config = (1 << 15) | (mux_list[0] << 12) | (pga << 9) | (0 << 8) | (data_rate << 5)
        config |= (1 << 3) | (0b01 << 1) | 1

        await self._write_config(config)
        await asyncio.sleep_ms(self._DELAY_MS[data_rate])

        self._mode = 'multi_scan'

    async def read_scan(self, gain = 1.0):
        """Read current channel + immediately start next channel
        Returns: (channel_index, voltage, raw, fsr)"""
        if self._mode != 'multi_scan':
            raise RuntimeError("Call start_continuous_scan() first")

        # 1. Read result of the channel we started last time
        raw = await self._read_raw()
        fsr = self._FSR[self._last_pga]
        voltage = raw * (fsr / 32768.0)
        voltage = round(voltage * gain, 4)
        current_idx = self._scan_idx

        # 2. Advance and start next channel (continuous mode)
        self._scan_idx = (self._scan_idx + 1) % len(self._scan_mux_list)
        next_mux = self._scan_mux_list[self._scan_idx]

        config = (1 << 15) | (next_mux << 12) | (self._last_pga << 9) | (0 << 8) | (self._last_dr << 5)
        config |= (1 << 3) | (0b01 << 1) | 1

        await self._write_config(config)
        # No sleep here → caller decides rate with asyncio.sleep_ms()

        return current_idx, voltage

    # ====================== TEMPERATURE ======================
    async def read_temperature(self):
        """Internal temperature sensor"""
        config = (1 << 15) | (1 << 8) | (self.DR_128SPS << 5) | (1 << 4)
        config |= (1 << 3) | (0b01 << 1) | 1

        await self._write_config(config)
        await asyncio.sleep_ms(5)

        raw = await self._read_raw()
        temp = raw * 0.03125
        temp = round(temp, 2)
        return temp

    def stop(self):
        """Stop any continuous / scan mode"""
        self._mode = None
        self._scan_mux_list = None


# ====================== EXAMPLE USAGE ======================
#async def main():
#    from machine import SPI, Pin
#
#    # === Change pins for your board ===
#    spi = SPI(1, baudrate=800_000, polarity=0, phase=1,
#              sck=Pin(18), mosi=Pin(23), miso=Pin(19))
#
#    adc = ADS1118(spi, cs_pin=5)   # or cs_pin=None
#
#    print("=== Multi-channel Continuous Scan (4 single-ended channels) ===")
#
#    mux_list = [
#        ADS1118.MUX_AIN0_GND,   # Ch0
#        ADS1118.MUX_AIN1_GND,   # Ch1
#        ADS1118.MUX_AIN2_GND,   # Ch2
#        ADS1118.MUX_AIN3_GND    # Ch3
#    ]
#
#    await adc.start_continuous_scan(mux_list,
#                                    pga=ADS1118.PGA_4_096V,
#                                    data_rate=ADS1118.DR_475SPS)
#
#    while True:
#        idx, v, raw, fsr = await adc.read_scan()
#        print(f"Ch{idx} (AIN{idx} vs GND): {v:+.6f} V   raw={raw}")
#        await asyncio.sleep_ms(40)   # your desired update rate (safe > conversion time)
#
#    # You can also mix with single-shot / temperature anytime