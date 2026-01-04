# master.py
import network, espnow, time
import asyncio
from machine import RTC, SoftSPI
from common.common import *
from common.logger import *
from lib.ACS71240 import *
from lib.ADS1118 import *
from lib.DS18B20 import *
from lib.RELAY import *
#from lib.CAN import * Wait for support in micropython-esp32
#from lib.SOC import BatterySOC, autosave_task
#from lib.battery_protection import BatteryProtection
#from lib.NTP import *
from lib.virt_slave import *
# ========================================
# CONFIG
# ========================================
WIFI_SSID = 'FRITZ!Box 7530 WC'
WIFI_PASS = "kramer89"

NTP_HOST = "pool.ntp.org"
NTP_PORT = 123
NTP_TIMEOUT = 5  # seconds
NTP_SYNC_INTERVAL = 3600

SLAVE_SYNC_INTERVAL = 10
SLAVE_TTL = 3600

# Pins
ADC_CURRENT_BAT_PIN = 4
CURRENT_FAULT_PIN = 5
BAT_FAULT_PIN = 10 #drives SiCs
OWM_TEMP_PIN = 9
SPI_SCLK_PIN = 6
SPI_MOSI_PIN = 7
SPI_MISO_PIN = 15
SPI_CS_PIN = 16
INT_REL0_PIN = 14
INT_REL1_PIN = 21

# ========================================
# INIT
# ========================================
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
#wlan.config(channel=1)

# Connect to Wi-Fi
print("Connecting to Wi-Fi...")
wlan.connect(WIFI_SSID, WIFI_PASS)
while not wlan.isconnected():
    time.sleep(0.5)
print("Wi-Fi connected. IP:", wlan.ifconfig()[0])

log = create_logger("system", level=LogLevel.INFO)
log.info("Startup system", ctx="boot")
# ========================================
# MAIN
# ========================================
async def main():
    print("Starting main application...")
    print("Config:", config_soc)
    # ESP-NOW
    e = espnow.ESPNow()
    e.active(True)
    # TODO:add watchdog
    rtc = RTC()
    slave_cfg = slave_config()
    slaves = Slaves(config = slave_cfg)
    e.irq(slaves.slave_listener)
    int_rel0 = Relay(pin=INT_REL0_PIN, active_high=False)
    int_rel1 = Relay(pin=INT_REL1_PIN, active_high=True)
    int_rel0.test(cycles=3, on_time=0.2, off_time=0.2)
    int_rel1.test(cycles=3, on_time=0.2, off_time=0.2)
    cur = ACS71240(viout_pin=ADC_CURRENT_BAT_PIN, fault_pin=CURRENT_FAULT_PIN)
    cur.calibrate_zero()
    spi = SoftSPI(baudrate=1000000, polarity=0, phase=0, sck=Pin(SPI_SCLK_PIN), mosi=Pin(SPI_MOSI_PIN), miso=Pin(SPI_MISO_PIN))
    vol = ADS1118(spi=spi, cs_pin = SPI_CS_PIN, channel_mux={0: 0b000, 1: 0b011}, gain=[1.0, 1.0]) #channel 0 = Bat, channel 1 = inv
    tmp = DS18B20(data_pin=OWM_TEMP_PIN, pullup=False)
    #can= BMSCan(config_can)
    #soc_estimator = BatterySOC(config_soc)
    #protector = BatteryProtection(config_prot, inverter_en_pin = BAT_FAULT_PIN ,current_sensor=cur, slaves=slaves)
    
    # Start tasks
    #ntp = ntp_sync(NTP_HOST, NTP_PORT, NTP_TIMEOUT, NTP_SYNC_INTERVAL, rtc)
    #ntp_sync_task = asyncio.create_task(ntp.ntp_task())
    #slave_sync_task = asyncio.create_task(slaves.sync_slaves_task(e))
    #slave_gc_task = asyncio.create_task(slaves.slave_gc())
    #await asyncio.sleep(60) # TODO: make this more sophisticated: Wait for slaves to connect and check plausability.

    #soc_auto_safe_task = asyncio.create_task(autosave_task(soc_estimator, 300))
    
    while True:
        current = cur.read_current(samples=10)
        print("Current:", current)
        bat_vol = await vol.read_voltage(channel=0)
        inv_vol = await vol.read_voltage(channel=1)
        vol_temp = await vol.read_temperature()
        print("Battery Voltage:", bat_vol, "Inverter Voltage:", inv_vol, "ADC Temp:", vol_temp)
        temp = tmp.get_temperatures()
        print("Temperatures:", temp)
        #v_cells = slaves.get_all_cell_voltages()
        #v_strings = slaves.get_all_str_voltages()
        #t_strings = slaves.get_all_str_temperatures()

        #soc = await soc_estimator.update(current, bat_vol, temp)

        #FIXME: protector should consider  and string temperatures.
        #prot_status = await protector.update(v_cells, bat_vol, current, temp, soc)
        #can_bus.send_status(prot_status)
        await asyncio.sleep(config_soc['sampling_interval'])

# ----------------------------------------------------------------------
#  Boot
# ----------------------------------------------------------------------
try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Stopped by user")