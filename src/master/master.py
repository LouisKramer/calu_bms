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
from common.credentials import *
#from lib.CAN import * Wait for support in micropython-esp32
from lib.SOC import BatterySOC, autosave_task
#from lib.battery_protection import BatteryProtection
from lib.NTP import *
from lib.virt_slave import *
import machine
from lib.BMSnow import BMSnowMaster
from lib.WLAN import WifiManager
# ========================================
# CONFIG
# ========================================
NTP_HOST = "pool.ntp.org"
NTP_PORT = 123
NTP_TIMEOUT = 5  # seconds
NTP_SYNC_INTERVAL = 3600

SLAVE_SYNC_INTERVAL = 10
SLAVE_TTL = 3600

# Pins
LED_USER = 18
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
wifi = WifiManager(
        ssid=WIFI_SSID,
        password=WIFI_PASS,
        hostname="bmsnow-master-01",
        led_pin=LED_USER)

time.sleep(5)
#wlan = network.WLAN(network.STA_IF)
#wlan.active(True)
## Connect to Wi-Fi
#print("Connecting to Wi-Fi...")
#led_user = machine.Pin(LED_USER, machine.Pin.OUT)
#wlan.connect(WIFI_SSID, WIFI_PASS)
#while not wlan.isconnected():
#    led_user.toggle()
#    print(".")
#    time.sleep(0.5)
#print("Wi-Fi connected. IP:", wlan.ifconfig()[0])
#log.info(f"Wlan channel: {wlan.config('channel')}", ctx="boot")
log = create_logger("system", level=LogLevel.INFO)
log.info("Startup system", ctx="boot")
# ========================================
# MAIN
# ========================================
async def main():
    wifi.start()
    log.info("Starting main application...", ctx="main")
    # TODO:add watchdog
    rtc = RTC()

    slaves = Slaves()
    master = BMSnowMaster(slaves=slaves)
    while True:
        await asyncio.sleep(2)

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
    soc_estimator = BatterySOC(default_soc_cfg)
    #protector = BatteryProtection(config_prot, inverter_en_pin = BAT_FAULT_PIN ,current_sensor=cur, slaves=slaves)
    
    # Start tasks
    ntp = ntp_sync(NTP_HOST, NTP_PORT, NTP_TIMEOUT, NTP_SYNC_INTERVAL)
    ntp_sync_task = asyncio.create_task(ntp.ntp_task())
    
    while slaves.nr_of_slaves == 0:
        slaves.discover_slaves(e)
        await asyncio.sleep(5)
    await asyncio.sleep(60) #wait for slaves to connect
    if slaves.nr_of_slaves() == 0:
        log.warn("No slaves connected after 60s, check connections!", ctx="main")
        #return  # Stop initialization if no slaves are connected
    else:
        log.info(f"{slaves.nr_of_slaves()} slaves connected.", ctx="main")

    #slave_sync_task = asyncio.create_task(slaves.sync_slaves_task(e))
    #slave_gc_task = asyncio.create_task(slaves.slave_gc())
    soc_auto_safe_task = asyncio.create_task(autosave_task(soc_estimator, 60))
    log.info("Initialization complete, entering main loop.", ctx="main")
    while True:
        slaves.request_data_from_slaves()
        current = cur.read_current(samples=10)
        log.info(f"Current: {current} A", ctx="main")
        bat_vol = await vol.read_voltage(channel=0)
        inv_vol = await vol.read_voltage(channel=1)
        vol_temp = await vol.read_temperature()
        log.info(f"Battery Voltage: {bat_vol}, Inverter Voltage: {inv_vol}, ADC Temp: {vol_temp}", ctx="main")
        temp = tmp.get_temperatures()
        log.info(f"Temperatures: {temp}", ctx="main")
        v_cells = slaves.get_all_cell_voltages()
        #v_strings = slaves.get_all_str_voltages()
        #t_strings = slaves.get_all_str_temperatures()
        avg_temp = sum(temp)/len(temp) if len(temp)>0 else 25.0 #change to sting temp
        soc = max(0, int(round(await soc_estimator.update(current, bat_vol, avg_temp))))
        log.info(f"Estimated SOC: {soc} %", ctx="main")

        #FIXME: protector should consider  and string temperatures.
        #prot_status = await protector.update(v_cells, bat_vol, current, temp, soc)
        #can_bus.send_status(prot_status)
        slaves.discover_slaves(e)# TODO: maybe pack into task
        await asyncio.sleep(default_soc_cfg['sampling_interval'])

# ----------------------------------------------------------------------
#  Boot
# ----------------------------------------------------------------------
try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Stopped by user")