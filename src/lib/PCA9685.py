import time
from machine import I2C

class PCA9685:
    # Register addresses
    MODE1 = 0x00
    MODE2 = 0x01
    PRESCALE = 0xFE
    LED0_ON_L = 0x06
    ALL_LED_ON_L = 0xFA
    
    def __init__(self, i2c, address=0x40):
        """Initialize PCA9685 with I2C interface and address."""
        self.i2c = i2c
        self.address = address
        self.reset()
    
    def reset(self):
        """Reset the PCA9685 to default settings."""
        self.i2c.writeto_mem(self.address, self.MODE1, bytearray([0x00]))
        time.sleep_ms(10)
    
    def set_pwm_freq(self, freq_hz):
        """Set PWM frequency in Hz (25 to 1526 Hz)."""
        # Calculate prescale value: round(25MHz / (4096 * freq_hz)) - 1
        prescale = int(round(25000000.0 / (4096 * freq_hz)) - 1)
        if prescale < 3 or prescale > 255:
            raise ValueError("Frequency out of range (25-1526 Hz)")
        
        # Read current MODE1 register
        mode1 = self.i2c.readfrom_mem(self.address, self.MODE1, 1)[0]
        
        # Set sleep bit to enter low power mode
        self.i2c.writeto_mem(self.address, self.MODE1, bytearray([mode1 | 0x10]))
        
        # Set prescale value
        self.i2c.writeto_mem(self.address, self.PRESCALE, bytearray([prescale]))
        
        # Clear sleep bit and enable auto-increment
        self.i2c.writeto_mem(self.address, self.MODE1, bytearray([mode1 & ~0x10 | 0x20]))
        time.sleep_ms(5)
    
    def set_pwm(self, channel, on, off):
        """Set PWM on and off times for a specific channel (0-15)."""
        if channel < 0 or channel > 15:
            raise ValueError("Channel must be 0-15")
        if on < 0 or on > 4095 or off < 0 or off > 4095:
            raise ValueError("On/Off values must be 0-4095")
        
        # Calculate register addresses for the channel
        reg = self.LED0_ON_L + 4 * channel
        # Write ON and OFF times (12-bit values, split into low and high bytes)
        data = bytearray([on & 0xFF, on >> 8, off & 0xFF, off >> 8])
        self.i2c.writeto_mem(self.address, reg, data)
    
    def set_all_pwm(self, on, off):
        """Set PWM on and off times for all channels."""
        if on < 0 or on > 4095 or off < 0 or off > 4095:
            raise ValueError("On/Off values must be 0-4095")
        
        # Write to ALL_LED registers
        data = bytearray([on & 0xFF, on >> 8, off & 0xFF, off >> 8])
        self.i2c.writeto_mem(self.address, self.ALL_LED_ON_L, data)
    
    def set_duty(self, channel, duty):
        """Set duty cycle (0-100%) for a specific channel."""
        if duty < 0 or duty > 100:
            raise ValueError("Duty cycle must be 0-100%")
        # Convert percentage to 12-bit value (0-4095)
        off = int(duty * 4095 / 100)
        self.set_pwm(channel, 0, off)
    
    def set_all_duty(self, duty):
        """Set duty cycle (0-100%) for all channels."""
        if duty < 0 or duty > 100:
            raise ValueError("Duty cycle must be 0-100%")
        off = int(duty * 4095 / 100)
        self.set_all_pwm(0, off)
    
    def off(self, channel):
        """Turn off a specific channel."""
        self.set_pwm(channel, 0, 0)
    
    def all_off(self):
        """Turn off all channels."""
        self.set_all_pwm(0, 0)
    
    def enable_odd_channels(self, duty, mask=None):
        """Enable specified odd-numbered channels (1, 3, ..., 15) with duty cycle.
        
        :param duty: Duty cycle (0-100%).
        :param mask: List or set of odd channels to enable (e.g., [1, 5]). If None, enable all odd channels.
        """
        if duty < 0 or duty > 100:
            raise ValueError("Duty cycle must be 0-100%")
        valid_odd_channels = set(range(1, 16, 2))  # {1, 3, 5, 7, 9, 11, 13, 15}
        if mask is not None:
            mask = set(mask)
            if not mask.issubset(valid_odd_channels):
                raise ValueError("Mask contains invalid odd channels. Must be subset of " + str(valid_odd_channels))
        else:
            mask = valid_odd_channels
        
        self.all_off()  # Turn off all channels first
        for channel in valid_odd_channels:
            if channel in mask:
                self.set_duty(channel, duty)
    
    def enable_even_channels(self, duty, mask=None):
        """Enable specified even-numbered channels (0, 2, ..., 14) with duty cycle.
        
        :param duty: Duty cycle (0-100%).
        :param mask: List or set of even channels to enable (e.g., [0, 4]). If None, enable all even channels.
        """
        if duty < 0 or duty > 100:
            raise ValueError("Duty cycle must be 0-100%")
        valid_even_channels = set(range(0, 16, 2))  # {0, 2, 4, 6, 8, 10, 12, 14}
        if mask is not None:
            mask = set(mask)
            if not mask.issubset(valid_even_channels):
                raise ValueError("Mask contains invalid even channels. Must be subset of " + str(valid_even_channels))
        else:
            mask = valid_even_channels
        # Turn off all channels first
        self.all_off()  
        # Turn on even channels masked 
        for channel in valid_even_channels:
            if channel in mask:
                self.set_duty(channel, duty)