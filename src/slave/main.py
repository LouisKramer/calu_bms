import time
import network
import mip
from common.credentials import WIFI_SSID, WIFI_PASS

FW_VERSION = "0.0.0.1"
HW_VERSION = "2.0.0.1"

print("start update...")
time.sleep(2)
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(WIFI_SSID, WIFI_PASS)
timeout = 10
while not wlan.isconnected() and timeout > 0:
    time.sleep(1)
    timeout -= 1

if wlan.isconnected():
    pass
    #TODO: check version and update if needed.
    #mip.install("github:LouisKramer/calu_bms/src/slave/package.json", target="/",version="dev")

wlan.disconnect()
print(f"Wlan channel: {wlan.config('channel')}")

import slave