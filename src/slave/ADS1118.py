from machine import Pin
import asyncio
import json
import os


class ADS1118:
    """
    MicroPython library for the ADS1118 16-bit ADC, supporting either SN74HC154 demultiplexer
    or single CS pin for chip selection, optimized for single-shot conversions with asynchronous reads.
    VCC is assumed to be 3.3V. Accepts an existing SPI instance.
    Calibration offsets are stored persistently in a JSON file and loaded at initialization.
    """
 
    # FSR positive values based on PGA, VCC=5V
    _FSR_5V = [5.0, 2.5, 1.25, 0.625, 0.3125, 0.15625, 0.078125, 0.078125]
    _FSR = [3.3, 3.3, 2.048, 1.024, 0.512, 0.256, 0.128, 0.064]

    # Data rates in SPS
    _DR_SPS = [8, 16, 32, 64, 128, 250, 475, 860]

    def __init__(
        self,
        spi,
        demux=None,
        demux_output=None,
        cs_pin=None,
        pga=2,
        dr=4,
        channel_mux = None,
        single_ended = True,
        pull_up_en=1,
        cal_file="ads1118_cal.json",
    ):
        """
        Initialize the ADS1118 with an SPI instance and either a demultiplexer or a single CS pin.

        :param spi: machine.SPI instance for communication.
        :param demux: SN74HC138 demultiplexer instance (optional, if cs_pin is None).
        :param demux_output: Demultiplexer output (0-15, required if demux is provided).
        :param cs_pin: GPIO pin number for direct CS control (optional, if demux is None).
        :param pga: Initial PGA setting (0-7).
        :param dr: Initial data rate setting (0-7).
        :param channel_mux: mux settings to be used on ADS1118 e.g. mux = {0: 0b111, 1: 0b110, 2: 0b101, 3: 0b100}
        :param pull_up_en: Enable pull-up on DOUT/DRDY (0 or 1).
        :param cal_file: File path for storing/loading calibration offsets.
        """
        if (demux is None and cs_pin is None) or (
            demux is not None and cs_pin is not None
        ):
            raise ValueError("Must provide either demux and demux_output or cs_pin")
        if demux is not None and (
            demux_output is None or demux_output < 0 or demux_output > 15
        ):
            raise ValueError(
                "Demux output must be between 0 and 7 if demux is provided"
            )
        if cs_pin is not None and (cs_pin < 0 or cs_pin > 47):  # ESP32-S3 has 48 GPIOs
            raise ValueError("CS pin must be a valid GPIO number (0-47)")
        if pga < 0 or pga > 7:
            raise ValueError("PGA must be between 0 and 7")
        if dr < 0 or dr > 7:
            raise ValueError("DR must be between 0 and 7")
        if channel_mux is None or len(channel_mux) == 0 or len(channel_mux) > 8:
            raise ValueError("Channel MUX must be provided and contain 1-8 entries")
        self.spi = spi
        self.demux = demux
        self.demux_output = demux_output
        self.cs_pin = Pin(cs_pin, Pin.OUT, value=1) if cs_pin is not None else None
        self.pga = pga
        self.dr = dr
        self.channel_mux = channel_mux
        self.nr_of_ch = len(channel_mux)
        self.pull_up_en = pull_up_en
        self.cal_file = cal_file
        self.offset = [0, 0, 0, 0]  # Signed offsets for channels 0, 1,2,3
        self._load_calibration()

    def _load_calibration(self):
        """Load calibration offsets from file, if available."""
        try:
            with open(self.cal_file, "r") as f:
                data = json.load(f)
                key = (
                    str(self.cs_pin)
                    if self.cs_pin is not None
                    else str(self.demux_output)
                )
                if key in data:
                    offsets = data[key]
                    if (
                        isinstance(offsets, list)
                        and len(offsets) == self.nr_of_ch
                        and all(isinstance(o, int) for o in offsets)
                    ):
                        self.offset = offsets
        except (OSError, ValueError):
            # File missing, corrupted, or invalid; keep default offsets [0, 0]
            pass

    def _save_calibration(self):
        """Save calibration offsets to file."""
        try:
            try:
                with open(self.cal_file, "r") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                data = {}
            key = (
                str(self.cs_pin) if self.cs_pin is not None else str(self.demux_output)
            )
            data[key] = self.offset
            with open(self.cal_file, "w") as f:
                json.dump(data, f)
        except OSError as e:
            print(f"Failed to save calibration: {e}")

    def validate_calibration(self, max_offset=1000):
        """
        Validate calibration offsets against a maximum absolute value.

        :param max_offset: Maximum allowed absolute offset (default 1000, ~3% of 16-bit range).
        :return: True if offsets are valid, False otherwise.
        """
        return all(abs(offset) <= max_offset for offset in self.offset)

    def clear_calibration(self):
        """Reset offsets to zero and remove from file."""
        self.offset = [0, 0, 0, 0]
        try:
            with open(self.cal_file, "r") as f:
                data = json.load(f)
            key = (
                str(self.cs_pin) if self.cs_pin is not None else str(self.demux_output)
            )
            if key in data:
                del data[key]
                with open(self.cal_file, "w") as f:
                    json.dump(data, f)
        except (OSError, ValueError):
            pass

    def set_pga(self, pga):
        """Set the PGA (gain)."""
        if pga < 0 or pga > 7:
            raise ValueError("PGA must be between 0 and 7")
        self.pga = pga

    def set_data_rate(self, dr):
        """Set the data rate."""
        if dr < 0 or dr > 7:
            raise ValueError("DR must be between 0 and 7")
        self.dr = dr

    def _build_config(self, ss, mux, ts):
        """Build the 16-bit config register value."""
        config = (
            (ss << 15)
            | (mux << 12)
            | (self.pga << 9)
            | (1 << 8)  # Mode=1 (single-shot)
            | (self.dr << 5)
            | (ts << 4)
            | (self.pull_up_en << 3)
            | (0b01 << 1)  # NOP=01
            | 0b1  # Reserved=1
        )
        return config

    def _write_and_read(self, config):
        """Perform SPI transaction: write config, read conversion result."""
        if self.demux is not None:
            self.demux.select(self.demux_output)
        elif self.cs_pin is not None:
            self.cs_pin.value(0)  # Active-low CS
        conf_bytes = bytearray([(config >> 8) & 0xFF, config & 0xFF])
        read_bytes = bytearray(2)
        self.spi.write_readinto(conf_bytes, read_bytes)
        if self.demux is not None:
            self.demux.deselect()
        elif self.cs_pin is not None:
            self.cs_pin.value(1)  # Deactivate CS
        return (read_bytes[0] << 8) | read_bytes[1]

    def _start_conversion(self, channel, ts):
        """Start a single-shot conversion by writing config with SS=1."""
        mux = self.channel_mux[channel] if ts == 0 else 0
        config = self._build_config(1, mux, ts)
        return self._write_and_read(config)  # Ignore returned data

    def _conversion_delay(self):
        """Return delay time in seconds for single-shot conversion."""
        return (1.0 / self._DR_SPS[self.dr]) + 0.01
    
    def get_conversion_delay(self):
        return self._conversion_delay()
    
    async def _read_raw(self, channel, ts, sleep = True):
        """Read raw 16-bit conversion result after async delay."""
        mux = self.channel_mux[channel] if ts == 0 else 0
        config = self._build_config(0, mux, ts)
        if sleep :
            await asyncio.sleep(self._conversion_delay())
        return self._write_and_read(config)

    def _get_value(self, raw, signed):
        if signed:
            if raw & 0x8000:  # Check MSB for negative values in differential mode
                return raw - 0x10000  # Convert to signed (-32768 to 32767)
            return raw
        else:
            return raw & 0x7FFF  # Mask MSB for 15-bit unsigned (0 to 32767)

    def _get_lsb(self, signed):
        """
        Get LSB size in volts based on mode.
        
        Returns:
            Float: LSB size in volts (FSR / 32768 for single-ended, FSR / 65536 for differential).
        """
        fsr = self._FSR[self.pga]
        if signed:
            return fsr / 32768  # 15-bit resolution for single-ended
        else:
            return fsr / 65536  # 16-bit resolution for differential

    async def calibrate(self, channel):
        """
        Calibrate zero point for the channel (stores offset persistently).

        :param channel: Channel (0 or 1).
        """
        if channel < 0 or channel > self.self.nr_of_ch:
            raise ValueError(f"Channel must be 0 to {self.self.nr_of_ch}")
        self._start_conversion(channel, 0)
        signed = await self._read(channel, 0)
        self.offset[channel] = signed
        self._save_calibration()

    async def _read(self, channel, ts=0, sleep = True):
        """Read signed conversion value."""
        raw = await self._read_raw(channel, ts, sleep)
        mux = self.channel_mux[channel]
        signed = (False if mux >= 4 else True)
        return self._get_value(raw, signed)

    async def read_voltage(self, channel):
        """Read voltage in single-shot mode."""
        if channel < 0 or channel > self.self.nr_of_ch:
            raise ValueError(f"Channel must be 0 to {self.self.nr_of_ch}")
        self._start_conversion(channel, 0)
        vol = await self._read(channel, 0) - self.offset[channel]
        mux = self.channel_mux[channel]
        signed = (False if mux >= 4 else True)
        voltage = vol * self._get_lsb(signed)
        return voltage

    async def read_temperature(self):
        """Read internal temperature sensor (single-shot)."""
        self._start_conversion(0, 1)
        raw = await self._read_raw(0, 1)
        signed = self._get_value(raw, True) >> 2
        temp = signed * 0.03125
        return temp
    
    async def read_voltage_all(self, channel):
        """Read all voltages helper. this function requires to call start_conversions_all first !!!!"""
        if channel < 0 or channel > self.self.nr_of_ch:
            raise ValueError(f"Channel must be 0 to {self.self.nr_of_ch}")
        vol = await self._read(channel, 0, sleep = False) - self.offset[channel]
        mux = self.channel_mux[channel]
        signed = (False if mux >= 4 else True)
        voltage = vol * self._get_lsb(signed)
        return voltage

    async def start_conversions_all(self, channel, ret = False):
        if channel < 0 or channel > self.self.nr_of_ch:
            raise ValueError(f"Channel must be 0 to {self.self.nr_of_ch}")
        if ret:
            vol = self._get_signed(self._start_conversion(channel, 0))- self.offset[channel]
            mux = self.channel_mux[channel]
            signed = (False if mux >= 4 else True)
            return vol * self._get_lsb(signed)
        else:
            self._start_conversion(channel, 0)


#######################################################################
## Main
#######################################################################
from machine import Pin, SoftSPI, SoftI2C
from SN74HC154 import SN74HC154
from ADS1118 import ADS1118
from PCA9685 import PCA9685
import asyncio

SLAVE_MAX = True

if SLAVE_MAX :
    NR_OF_ADCS = 8
    NR_OF_PCA = 2
else:
    NR_OF_ADCS = 4
    NR_OF_PCA = 1

# Initialize I2C for PCA9685
i2c = SoftI2C(scl=Pin(9), sda=Pin(8), freq=400000)  # I2C0, 400 kHz

# Initialize SPI for ADS1118
spi = SoftSPI(
    baudrate=1000000,
    polarity=0,
    phase=0,
    sck=Pin(10),
    mosi=Pin(11),
    miso=Pin(12),
)

# Initialize SN74HC154 demultiplexer (GPIO pins 0, 1, 2, 3 for A0-A3, enable on GP4)
demux = SN74HC154(enable_pin=4, a0_pin=0, a1_pin=1, a2_pin=2, a3_pin=3)

# Initialize PCA9685
pcas = [PCA9685(i2c, address=0x40 + i) for i in range(NR_OF_PCA)]
for pca in pcas:
    pca.set_pwm_freq(100)  # 100 Hz PWM

# Initialize 8 ADS1118 instances
mux = {0: 0b111, 1: 0b110, 2: 0b101, 3: 0b100}
adcs = [
    ADS1118(spi=spi, demux=demux, demux_output=i, pga=2, dr=4, channel_mux=mux)
    for i in range(NR_OF_ADCS)
]

mux = {0: 0b100}
adc_string_0 = ADS1118(spi=spi, demux=demux, demux_output=8, pga=2, dr=7, channel_mux=mux)
adc_string_1 = ADS1118(spi=spi, demux=demux, demux_output=9, pga=2, dr=7, channel_mux=mux)

def start_all_even_adc_conversions():
    for i, adc in enumerate(adcs):
        adc.start_conversions_all(0)

def start_all_odd_adc_conversions():
    for i, adc in enumerate(adcs):
        adc.start_conversions_all(1)

def read_all_even_adc_channels():
    voltages = []
    for i, adc in enumerate(adcs):
        voltages.append(adc.read_voltage_all(0))
    return voltages

def read_all_odd_adc_channels():
    voltages = []
    for i, adc in enumerate(adcs):
        voltages.append(adc.read_voltage_all(1))
    return voltages


async def read_all_adc():
    num_adcs = len(adcs)
    num_channels = adcs[0].nr_of_ch
    if not all(adc.nr_of_ch == num_channels for adc in adcs):
        raise ValueError("All ADCs must have the same number of channels")
    vol = [0] * (num_adcs * num_channels)
    
    # Initialize pipeline
    for adc in adcs:
        try:
            adc.start_conversions_all(channel=0, ret=False)
        except Exception as e:
            print(f"Error initializing ADC: {e}")
    

    # Read all channels
    for j in range(num_channels):
        channel = (j + 1) % num_channels
        for i, adc in enumerate(adcs):
            try:
                vol[j + i * num_channels] = adc.start_conversions_all(channel=channel, ret=True)

            except Exception as e:
                print(f"Error reading ADC {i} channel {j}: {e}")
                vol[j + i * num_channels] = None
        #wait to complete conversion.
        # SPI @1MHz and 2 bytes takes adc_read_time = ~100us (16us for 2 bytes, rest overhead)
        # @ 128 SPS every ~8ms a new value
        # --> one round trip should at least last: 10ms
        # whitout delay: nr_of_adcs * adc_read_time
        asyncio.sleep(adc.get_conversion_delay() - (num_adcs * 0.0001))
    # total roundtrip time = num_channels * (conversion_delay - (nr_of_adcs * adc_read_time))
    # trt = ~70ms
    return vol

async def main():
    odd_mask  = [0] * 16
    even_mask = [0] * 16
    # Optional: Calibrate all ADCs once at startup (assuming inputs shorted)
    for adc in adcs:
        await adc.calibrate(0)
        await adc.calibrate(1)

    while True:
        # Enable odd PCA9685 channels (1, 3, ..., 15)
        for pca in pcas:
            pca.enable_odd_channels(50, mask=odd_mask)
        await asyncio.sleep(0.3)
        # Step 3: Enable even PCA9685 channels (0, 2, ..., 14)
        for pca in pcas:
            pca.enable_even_channels(50, mask=even_mask)
        await asyncio.sleep(0.3)

        voltages = read_all_adc()
        string_vol_0 = await adc_string_0.read_voltage(channel = 0)
        string_vol_1 = await adc_string_1.read_voltage(channel = 0)

        # Read string voltage ADS1118 without demux
        # Read temperatures DS18B20
        # Check for over temperature
        # Check for String OV,UV
        # Check for OV=3.6V UV=2.6V
        # build odd_mask bal_th = 3.4V ,bal_diff_th = 0.2V
        # build even_mask bal_th = 3.4V ,bal_diff_th = 0.2V


# Run the async loop
asyncio.run(main())
