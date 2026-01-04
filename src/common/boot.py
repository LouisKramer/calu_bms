# This file is executed on every boot (including wake-boot from deepsleep)
#import esp
#esp.osdebug(None)
import machine

# Connect to Wi-Fi
print("Booting...")
led = machine.Pin(18, machine.Pin.OUT)
led.off()
print("Boot complete.")