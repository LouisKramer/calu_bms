# This file is executed on every boot (including wake-boot from deepsleep)
#import esp
#esp.osdebug(None)
import webrepl
import machine
import network
import time
webrepl.start()

# Connect to Wi-Fi
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect('FRITZ!Box 7530 WC', 'kramer89')
timeout = 10
while not wlan.isconnected() and timeout > 0:
   time.sleep(1)
   timeout -= 1
if wlan.isconnected():
   print('Wi-Fi connected:', wlan.ifconfig())
   led = machine.Pin(14, machine.Pin.OUT)
   led.off()
else:
   led = machine.Pin(4, machine.Pin.OUT)
   led.off()