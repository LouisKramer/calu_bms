# boot.py (slave HW 2.0.1.0) - executed on every boot, before main.py
from machine import Pin, SoftI2C

Pin(39, Pin.OUT, value=1)   # LED_ERR off (active low)
Pin(40, Pin.OUT, value=1)   # LED_USR off (active low)
Pin(10, Pin.OUT, value=1)   # SN74HC154 disabled -> no ADS1118 selected

# The PCA9685s are supplied from +5V and keep their outputs across an ESP32 reset:
# switch all balancing outputs off (ALL_LED_OFF_H full-off bit) as early as possible.
_i2c = SoftI2C(scl=Pin(11), sda=Pin(3), freq=100_000)
for _a in (0x40, 0x41):
    try:
        _i2c.writeto_mem(_a, 0xFD, b"\x10")
    except OSError:
        print("boot: PCA9685 0x%02x not responding" % _a)
del _i2c, _a
print("Boot complete.")
