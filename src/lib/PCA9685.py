# PCA9685.py - 16-channel 12-bit PWM driver (used for balancing outputs)
import time


class PCA9685:
    MODE1 = 0x00
    MODE2 = 0x01
    LED0_ON_L = 0x06
    ALL_LED_ON_L = 0xFA
    PRESCALE = 0xFE

    MODE1_SLEEP = 0x10
    MODE1_AI = 0x20        # register auto-increment
    MODE1_ALLCALL = 0x01   # responds to 0x70 (power-on default, kept)
    MODE2_OUTDRV = 0x04    # totem-pole outputs
    FULL = 0x10            # bit 4 of LEDn_ON_H / LEDn_OFF_H

    def __init__(self, i2c, address=0x40, freq=None, reset=True):
        self.i2c = i2c
        self.address = address
        if reset:
            self.reset(freq)

    def _w(self, reg, data):
        self.i2c.writeto_mem(self.address, reg, bytes(data))

    def probe(self):
        try:
            self.i2c.readfrom_mem(self.address, self.MODE1, 1)
            return True
        except OSError:
            return False

    def reset(self, freq=None):
        """All outputs off, totem-pole drive, optional PWM frequency, oscillator running."""
        self._w(self.MODE1, (self.MODE1_SLEEP | self.MODE1_AI | self.MODE1_ALLCALL,))
        self._w(self.MODE2, (self.MODE2_OUTDRV,))
        self.all_off()
        if freq:
            self._w(self.PRESCALE, (self._prescale(freq),))   # only writable while sleeping
        self._w(self.MODE1, (self.MODE1_AI | self.MODE1_ALLCALL,))
        time.sleep_ms(1)   # oscillator start-up (500 us)

    @staticmethod
    def _prescale(freq):
        p = int(25_000_000 / (4096 * freq) + 0.5) - 1
        if not 3 <= p <= 255:
            raise ValueError("PWM frequency must be 24..1526 Hz")
        return p

    def set_pwm_freq(self, freq):
        self.reset(freq)

    def set_pwm(self, channel, on, off):
        """Raw counts 0..4095 within the PWM period."""
        if not 0 <= channel <= 15:
            raise ValueError("channel must be 0..15")
        if not (0 <= on <= 4095 and 0 <= off <= 4095):
            raise ValueError("on/off must be 0..4095")
        self._w(self.LED0_ON_L + 4 * channel, (on & 0xFF, on >> 8, off & 0xFF, off >> 8))

    def set_duty(self, channel, duty):
        """Duty cycle in percent (0..100); 0 and 100 use the full-off / full-on bits."""
        if not 0 <= duty <= 100:
            raise ValueError("duty must be 0..100 %")
        if duty == 0:
            self.off(channel)
        elif duty == 100:
            self._w(self.LED0_ON_L + 4 * channel, (0, self.FULL, 0, 0))
        else:
            self.set_pwm(channel, 0, max(1, int(duty * 4096 / 100)))

    def off(self, channel):
        if not 0 <= channel <= 15:
            raise ValueError("channel must be 0..15")
        self._w(self.LED0_ON_L + 4 * channel, (0, 0, 0, self.FULL))

    def all_off(self):
        self._w(self.ALL_LED_ON_L, (0, 0, 0, self.FULL))

    def is_off(self, channel):
        """True if the channel's full-off bit is set (read back from the device)."""
        return bool(self.i2c.readfrom_mem(self.address, self.LED0_ON_L + 4 * channel + 3, 1)[0] & self.FULL)
