# PCA9685.py – Improved MicroPython driver for PCA9685 16-channel PWM controller
import ustruct
import time


class PCA9685:
    # Registers
    MODE1 = 0x00
    MODE2 = 0x01
    PRESCALE = 0xFE
    LED0_ON_L = 0x06

    # Mode1 bits
    MODE1_RESTART = 0x80
    MODE1_SLEEP = 0x10
    MODE1_AI = 0x20   # Auto-increment

    # Mode2 bits
    MODE2_OUTDRV = 0x04   # Totem-pole output
    MODE2_INVRT = 0x00
    MODE2_OUTNE = 0x01    # When OE=1 → high-Z

    def __init__(self, i2c, address=0x40):
        self.i2c = i2c
        self.address = address
        self._reset()
        self._init_mode()

    def _reset(self):
        """Full software reset as per datasheet"""
        self._write(self.MODE1, 0x06)   # SWRST
        time.sleep_us(10)

    def _init_mode(self):
        """Configure MODE1 + MODE2 once"""
        self._write(self.MODE1, self.MODE1_AI | self.MODE1_RESTART)
        self._write(self.MODE2, self.MODE2_OUTDRV | self.MODE2_OUTNE)

    def _write(self, reg: int, value: int):
        self.i2c.writeto_mem(self.address, reg, bytearray([value]))

    def _read(self, reg: int) -> int:
        return self.i2c.readfrom_mem(self.address, reg, 1)[0]

    def freq(self, freq: int | None = None) -> int | None:
        """Set or get PWM frequency (Hz). Range 24–1526 Hz."""
        if freq is None:
            prescale = self._read(self.PRESCALE)
            return int(25_000_000.0 / 4096.0 / (prescale + 1) + 0.5)

        if not 24 <= freq <= 1526:
            raise ValueError("Frequency must be between 24 and 1526 Hz")

        prescale = int(25_000_000.0 / 4096.0 / freq + 0.5) - 1
        if prescale < 3 or prescale > 255:
            raise ValueError("Invalid frequency")

        # Go to sleep
        old_mode = self._read(self.MODE1)
        self._write(self.MODE1, (old_mode & 0x7F) | self.MODE1_SLEEP)
        time.sleep_us(5)

        self._write(self.PRESCALE, prescale)

        # Wake up
        self._write(self.MODE1, old_mode | self.MODE1_RESTART)
        time.sleep_us(5)

    def pwm(self, index: int, on: int | None = None, off: int | None = None):
        """Set or get raw ON/OFF values for a channel (0-15)"""
        if not 0 <= index <= 15:
            raise ValueError("Channel index 0-15 only")

        reg = self.LED0_ON_L + 4 * index

        if on is None or off is None:
            data = self.i2c.readfrom_mem(self.address, reg, 4)
            return ustruct.unpack('<HH', data)

        if not (0 <= on <= 4096 and 0 <= off <= 4096):
            raise ValueError("ON/OFF must be 0-4096")
        data = ustruct.pack('<HH', on, off)
        self.i2c.writeto_mem(self.address, reg, data)

    def duty(self, index: int, value: int | None = None, invert: bool = False):
        """Set or get duty cycle 0-4095 (or 0.0-1.0 if float)"""
        if not 0 <= index <= 15:
            raise ValueError("Channel index 0-15 only")

        if value is None:
            on, off = self.pwm(index)
            if on == 0 and off == 4096:      # full off
                val = 0
            elif on == 4096 and off == 0:    # full on
                val = 4095
            else:
                val = off
            return 4095 - val if invert else val

        # Normalize float 0.0-1.0 to int 0-4095
        if isinstance(value, float):
            value = int(value * 4095 + 0.5)
        if not 0 <= value <= 4095:
            raise ValueError("Duty must be 0-4095 (or 0.0-1.0)")

        if invert:
            value = 4095 - value

        if value == 0:
            self.pwm(index, 0, 4096)          # full off
        elif value == 4095:
            self.pwm(index, 4096, 0)          # full on
        else:
            self.pwm(index, 0, value)

    # ====================== Extra useful methods ======================

    def sleep(self):
        """Put PCA9685 into low-power sleep mode"""
        mode = self._read(self.MODE1)
        self._write(self.MODE1, mode | self.MODE1_SLEEP)

    def wake(self):
        """Wake from sleep mode"""
        mode = self._read(self.MODE1)
        self._write(self.MODE1, (mode & ~self.MODE1_SLEEP) | self.MODE1_RESTART)

    def all_duty(self, value: int, invert: bool = False):
        """Set same duty on ALL 16 channels (very fast)"""
        if isinstance(value, float):
            value = int(value * 4095 + 0.5)
        if not 0 <= value <= 4095:
            raise ValueError("Duty 0-4095")

        if invert:
            value = 4095 - value

        if value == 0:
            on, off = 0, 4096
        elif value == 4095:
            on, off = 4096, 0
        else:
            on, off = 0, value

        data = ustruct.pack('<HH', on, off)
        # Use auto-increment to write all 16 channels in one I2C transaction
        self.i2c.writeto_mem(self.address, self.LED0_ON_L, data * 16)


# ====================== Example usage ======================
# pca = PCA9685(i2c)
# pca.freq(50)           # 50 Hz for servos
# pca.duty(0, 0.5)       # 50% on channel 0
# pca.all_duty(0.1)      # all LEDs at 10%