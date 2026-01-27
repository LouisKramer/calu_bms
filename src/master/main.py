import time
import network
import mip
from common.credentials import WIFI_SSID, WIFI_PASS

FW_VERSION = "0.0.0.1"
HW_VERSION = "1.4.0.1"

print("start update...")
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(WIFI_SSID, WIFI_PASS)
timeout = 10
print("Connecting...")
while not wlan.isconnected() and timeout > 0:
    time.sleep(1)
    timeout -= 1

if wlan.isconnected():
    print("Connected! Checking for updates...")
    pass
    #TODO: check version and update if needed.
    #mip.install("github:LouisKramer/calu_bms/src/master/package.json", target="/",version="dev")
    #mip.install('github:ederjc/uhome/uhome/uhome.py')

wlan.disconnect()
import master