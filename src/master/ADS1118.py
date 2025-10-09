#Create a fully featured micropython library for this sensor with the following requirements:
#- The Sensor shall operate in differential mode where channel 0,1 and 2,3 are paired. 
#- The library shall support single and continuous voltage read mode
#- VCC is 3.3V.  
#- Target device shall be an ESP32-S3-WROOM-1-N8R8. 
#- The SPI pins shall be configurable.  
#- The library shall have a calibration function to set the zero point
#- PGA and DR should be configurable
#- add function to read temperature

import machine
import time

class ADS1118:
    """
    MicroPython library for the ADS1118 16-bit ADC.
    
    Supports differential mode with paired channels (0: AIN0-AIN1, 1: AIN2-AIN3).
    VCC is assumed to be 3.3V.
    SPI pins are configurable.
    Supports single-shot and continuous conversion modes.
    PGA and data rate are configurable.
    Includes calibration for zero point offset per channel.
    Includes function to read internal temperature.
    """

    # MUX settings for differential pairs
    _MUX = {
        0: 0b000,  # AIN0 - AIN1
        1: 0b011   # AIN2 - AIN3
    }

    # FSR positive values based on PGA
    _FSR = [6.144, 4.096, 2.048, 1.024, 0.512, 0.256, 0.256, 0.256]

    # Data rates in SPS
    _DR_SPS = [8, 16, 32, 64, 128, 250, 475, 860]

    def __init__(self, spi_bus=1, sck_pin=10, mosi_pin=11, miso_pin=12, cs_pin=13, baudrate=1000000, pga=2, dr=4, pull_up_en=1):
        """
        Initialize the ADS1118.
        
        :param spi_bus: SPI bus ID (1 or 2 on ESP32).
        :param sck_pin: SCK pin number.
        :param mosi_pin: MOSI (DIN) pin number.
        :param miso_pin: MISO (DOUT/DRDY) pin number.
        :param cs_pin: CS pin number.
        :param baudrate: SPI baudrate (max 4000000).
        :param pga: Initial PGA setting (0-7).
        :param dr: Initial data rate setting (0-7).
        :param pull_up_en: Enable pull-up on DOUT/DRDY (0 or 1).
        """
        if pga < 0 or pga > 7:
            raise ValueError("PGA must be between 0 and 7")
        if dr < 0 or dr > 7:
            raise ValueError("DR must be between 0 and 7")
        
        self.spi = machine.SPI(
            spi_bus,
            baudrate=baudrate,
            polarity=0,
            phase=0,
            sck=machine.Pin(sck_pin),
            mosi=machine.Pin(mosi_pin),
            miso=machine.Pin(miso_pin)
        )
        self.cs = machine.Pin(cs_pin, machine.Pin.OUT, value=1)
        self.miso = machine.Pin(miso_pin, machine.Pin.IN)  # For reading DRDY level
        self.pga = pga
        self.dr = dr
        self.pull_up_en = pull_up_en
        self.offset = [0, 0]  # Signed offsets for each channel
        self._continuous_mode = False
        self._current_channel = None

    def set_pga(self, pga):
        """
        Set the PGA (gain).
        
        :param pga: PGA value (0-7).
        """
        if pga < 0 or pga > 7:
            raise ValueError("PGA must be between 0 and 7")
        self.pga = pga

    def set_data_rate(self, dr):
        """
        Set the data rate.
        
        :param dr: Data rate value (0-7).
        """
        if dr < 0 or dr > 7:
            raise ValueError("DR must be between 0 and 7")
        self.dr = dr

    def _build_config(self, ss, mux, mode, ts):
        """
        Build the 16-bit config register value.
        
        :param ss: Single-start bit (0 or 1).
        :param mux: MUX value (0b000 or 0b011).
        :param mode: Mode (0: continuous, 1: single-shot).
        :param ts: TS_MODE (0: ADC, 1: temperature).
        :return: 16-bit config value.
        """
        config = (
            (ss << 15) |
            (mux << 12) |
            (self.pga << 9) |
            (mode << 8) |
            (self.dr << 5) |
            (ts << 4) |
            (self.pull_up_en << 3) |
            (0b01 << 1) |  # NOP=01
            0b1  # Reserved=1
        )
        return config

    def _write_and_read(self, config):
        """
        Perform SPI transaction: write config, read conversion result.
        
        :param config: 16-bit config to write.
        :return: 16-bit raw conversion result.
        """
        conf_bytes = bytearray([(config >> 8) & 0xFF, config & 0xFF])
        read_bytes = bytearray(2)
        self.cs.value(0)
        self.spi.write_readinto(conf_bytes, read_bytes)
        self.cs.value(1)
        return (read_bytes[0] << 8) | read_bytes[1]

    def _start_conversion(self, channel, mode, ts):
        """
        Start a conversion by writing config with SS=1.
        
        :param channel: Channel (0 or 1) or dummy for temp.
        :param mode: Mode (0 or 1).
        :param ts: TS_MODE (0 or 1).
        """
        mux = self._MUX[channel] if ts == 0 else 0  # MUX ignored in temp mode
        config = self._build_config(1, mux, mode, ts)  # SS=1
        self._write_and_read(config)  # Ignore returned data

    def _wait_drdy(self):
        """
        Wait for DRDY (DOUT low when CS high).
        """
        # Approximate wait time based on data rate
        wait_ms = int(1000 / self._DR_SPS[self.dr]) + 10
        start_time = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start_time) < 1000:  # Timeout 1s
            if self.miso.value() == 0:
                return
            time.sleep_ms(1)
        raise TimeoutError("DRDY timeout")

    def _read_raw(self, channel, mode, ts):
        """
        Read raw 16-bit conversion result.
        
        :param channel: Channel (0 or 1) or dummy.
        :param mode: Mode (0 or 1).
        :param ts: TS_MODE (0 or 1).
        :return: Raw 16-bit value.
        """
        mux = self._MUX[channel] if ts == 0 else 0
        config = self._build_config(0, mux, mode, ts)  # SS=0
        return self._write_and_read(config)

    def _get_signed(self, raw):
        """
        Convert raw 16-bit to signed integer.
        
        :param raw: Raw 16-bit value.
        :return: Signed integer.
        """
        if raw & 0x8000:
            return raw - 0x10000
        return raw

    def _get_lsb(self):
        """
        Get LSB size in volts.
        
        :return: LSB voltage.
        """
        fsr = self._FSR[self.pga]
        return fsr / 32768

    def calibrate(self, channel):
        """
        Calibrate zero point for the channel (stores offset).
        
        :param channel: Channel (0 or 1).
        """
        if channel not in [0, 1]:
            raise ValueError("Channel must be 0 or 1")
        signed = self._read_signed(channel, single=True)
        self.offset[channel] = signed

    def _read_signed(self, channel, single, ts=0):
        """
        Read signed conversion value.
        
        :param channel: Channel (0 or 1).
        :param single: True for single-shot, False for continuous.
        :param ts: TS_MODE.
        :return: Signed integer.
        """
        mode = 1 if single else 0
        raw = self._read_raw(channel, mode, ts)
        return self._get_signed(raw)

    def read_voltage(self, channel=None):
        """
        Read voltage in single-shot or continuous mode.
        
        In continuous mode, channel is ignored (uses started channel).
        
        :param channel: Channel (0 or 1) for single-shot.
        :return: Voltage in volts.
        """
        if self._continuous_mode:
            if channel is not None:
                raise ValueError("Channel ignored in continuous mode")
            channel = self._current_channel
            single = False
        else:
            if channel is None:
                raise ValueError("Channel required in single-shot mode")
            if channel not in [0, 1]:
                raise ValueError("Channel must be 0 or 1")
            single = True

        if single:
            self._start_conversion(channel, 1, 0)
            self._wait_drdy()

        signed = self._read_signed(channel, single, 0) - self.offset[channel]
        voltage = signed * self._get_lsb()
        return voltage

    def start_continuous(self, channel):
        """
        Start continuous conversion mode on a channel.
        
        :param channel: Channel (0 or 1).
        """
        if channel not in [0, 1]:
            raise ValueError("Channel must be 0 or 1")
        self._start_conversion(channel, 0, 0)
        self._current_channel = channel
        self._continuous_mode = True

    def stop_continuous(self):
        """
        Stop continuous mode (switches to single-shot power-down).
        """
        # Write config with mode=1 to power down
        if self._continuous_mode:
            config = self._build_config(0, self._MUX[self._current_channel], 1, 0)
            self._write_and_read(config)
            self._continuous_mode = False
            self._current_channel = None

    def read_temperature(self):
        """
        Read internal temperature sensor (single-shot).
        
        :return: Temperature in °C.
        """
        self._start_conversion(0, 1, 1)  # Dummy channel
        self._wait_drdy()
        raw = self._read_raw(0, 1, 0)  # Read with TS=0 for next if needed
        signed = self._get_signed(raw) >> 2
        temp = signed * 0.03125
        return temp
# Example usage
"""
# Initialize the ADC with default pins for ESP32-S3 SPI1
adc = ADS1118(spi_bus=1, sck_pin=10, mosi_pin=11, miso_pin=12, cs_pin=13, pga=2, dr=0)  # PGA= ±2.048V, DR=8 SPS

# Set PGA and data rate if needed
adc.set_pga(4)  # ±0.512V
adc.set_data_rate(7)  # 860 SPS

# Calibrate channel 0 (assume inputs shorted for zero)
adc.calibrate(0)

# Single-shot voltage read on channel 0
voltage = adc.read_voltage(0)
print("Voltage on channel 0:", voltage, "V")

# Read internal temperature
temperature = adc.read_temperature()
print("Internal temperature:", temperature, "°C")

# Start continuous mode on channel 1
adc.start_continuous(1)

# Read voltages in loop
for _ in range(5):
    voltage = adc.read_voltage()
    print("Continuous voltage on channel 1:", voltage, "V")
    time.sleep(0.5)

# Stop continuous mode
adc.stop_continuous()
"""