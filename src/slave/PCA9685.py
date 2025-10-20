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