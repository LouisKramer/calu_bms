# master.py
import network, espnow, time
import asyncio
from machine import RTC, SoftSPI
from common.credentials import *
from common.common import *
from common.logger import *
Logger.init(syslog_host=SYSLOG_HOST)
from lib.ACS71240 import *
from lib.ADS1118 import *
from lib.DS18B20 import *
from lib.RELAY import *
from lib.SOC import BatterySOC, autosave_task
from lib.NTP import *
from lib.virt_slave import *
from lib.BMSnow import BMSnowMaster
from lib.WLAN import WlanManager
#from lib.CAN import * Wait for support in micropython-esp32
#from lib.battery_protection import BatteryProtection
# ========================================
# CONFIG
# ========================================
SLAVE_SYNC_INTERVAL = 10
SLAVE_TTL = 3600

# Pins
ADC_CURRENT_BAT_PIN = 4
CURRENT_FAULT_PIN = 5 #input for overcurrent 
BAT_FAULT_PIN = 10 #Output for driving sic and safe relay

SPI_SCLK_PIN = 6
SPI_MOSI_PIN = 7
SPI_MISO_PIN = 15
SPI_CS_PIN = 16
OWM_TEMP_PIN = 9

BUZZER_PIN = 17
LED_USER_PIN = 18
LED_ERR_PIN = 8

INT_REL0_PIN = 14
INT_REL1_PIN = 21
EXT_REL0_PIN = 11

CAN_TX_PIN = 40
CAN_RX_PIN = 39

# ========================================
# INIT
# ========================================
log = Logger()
log.info("Starting wifi manager")
wifi = WlanManager(ssid=WIFI_SSID, password=WIFI_PASS, hostname=WIFI_HOST, led_pin=LED_USER_PIN)
wifi.start()
rtc = RTC()
log.info("Startup system")
# ========================================
# MAIN
# ========================================
async def main():
    log.info("Starting main application")

    # TODO:add watchdog
    slaves = Slaves()
    master = BMSnowMaster(slaves=slaves)
    master.start()

    int_rel0 = Relay(pin=INT_REL0_PIN, active_high=True)
    int_rel1 = Relay(pin=INT_REL1_PIN, active_high=True)
    ext_rel0 = Relay(pin=EXT_REL0_PIN, active_high=True)
    int_rel0.test(cycles=3, on_time=0.05, off_time=0.05)
    int_rel1.test(cycles=3, on_time=0.05, off_time=0.05)
    ext_rel0.test(cycles=3, on_time=0.05, off_time=0.05)
    cur = ACS71240(viout_pin=ADC_CURRENT_BAT_PIN, fault_pin=CURRENT_FAULT_PIN)
    cur.calibrate_zero()
    spi = SoftSPI(baudrate=1000000, polarity=0, phase=0, sck=Pin(SPI_SCLK_PIN), mosi=Pin(SPI_MOSI_PIN), miso=Pin(SPI_MISO_PIN))
    vol = ADS1118(spi=spi, cs_pin = SPI_CS_PIN, channel_mux={0: 0b000, 1: 0b011}, gain=[1.0, 1.0]) #channel 0 = Bat, channel 1 = inv
    tmp = DS18B20(data_pin=OWM_TEMP_PIN, pullup=False)
    soc_estimator = BatterySOC(default_soc_cfg)
    soc_auto_safe_task = asyncio.create_task(autosave_task(soc_estimator, 60))
    #can= BMSCan(config_can)
    #protector = BatteryProtection(config_prot, inverter_en_pin = BAT_FAULT_PIN ,current_sensor=cur, slaves=slaves)
    
    # Start tasks
    ntp = ntp_sync(NTP_HOST, NTP_PORT, NTP_TIMEOUT, NTP_SYNC_INTERVAL)
    ntp_sync_task = asyncio.create_task(ntp.ntp_task())

    #slave_sync_task = asyncio.create_task(slaves.sync_slaves_task(e))
    #slave_gc_task = asyncio.create_task(slaves.slave_gc())
    
    log.info("Initialization complete, entering main loop.")

    while True:
        master.request_all_data()
        current = cur.read_current(samples=10)
        log.info(f"Current: {current} A")
        bat_vol = await vol.read_voltage(channel=0)
        inv_vol = await vol.read_voltage(channel=1)
        vol_temp = await vol.read_temperature()
        log.info(f"Battery Voltage: {bat_vol}, Inverter Voltage: {inv_vol}, ADC Temp: {vol_temp}")
        temp = tmp.get_temperatures()
        log.info(f"Temperatures: {temp}")

        avg_temp = sum(temp)/len(temp) if len(temp)>0 else 25.0 #change to sting temp
        soc = max(0, int(round(await soc_estimator.update(current, bat_vol, avg_temp))))
        log.info(f"Estimated SOC: {soc} %")

        #FIXME: protector should consider  and string temperatures.
        #prot_status = await protector.update(v_cells, bat_vol, current, temp, soc)
        #can_bus.send_status(prot_status)
        for s in slaves:
            log.info(f"Voltages: {s.battery.meas.vcell}")
        await asyncio.sleep(default_soc_cfg['sampling_interval'])

# ----------------------------------------------------------------------
#  Boot
# ----------------------------------------------------------------------
try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Stopped by user")