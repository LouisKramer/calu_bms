# boot.py (slave HW 2.0.1.0) - executed on every boot
from machine import Pin

# Safe pin states before main.py runs
Pin(39, Pin.OUT, value=1)   # LED_ERR off (active low)
Pin(40, Pin.OUT, value=1)   # LED_USR off (active low)
Pin(10, Pin.OUT, value=1)   # SN74HC154 disabled -> no ADS1118 selected
print("Boot complete.")
