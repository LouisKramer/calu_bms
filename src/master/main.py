import time
import network
import mip
from common.credentials import WIFI_SSID, WIFI_PASS
print("start update...")
time.sleep(10)
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(WIFI_SSID, WIFI_PASS)
while not wlan.isconnected():
    time.sleep(1)
mip.install("github:LouisKramer/calu_bms/src/master/package.json", target="/",version="dev")
mip.install('github:ederjc/uhome/uhome/uhome.py')
import master