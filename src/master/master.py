# master.py
import network, espnow, time
import asyncio
from common.HAL import master_hal as HAL
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
from lib.PROT import Protector

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
    protector = Protector()
    meas = master_data()
    # TODO:add watchdog
    slave_handler = BMSnowMaster()
    slave_handler.start()

    int_rel0 = Relay(pin=HAL.INT_REL0_PIN, active_high=True)
    int_rel1 = Relay(pin=HAL.INT_REL1_PIN, active_high=True)
    ext_rel0 = Relay(pin=HAL.EXT_REL0_PIN, active_high=True)
    int_rel0.test(cycles=3, on_time=0.05, off_time=0.05)
    int_rel1.test(cycles=3, on_time=0.05, off_time=0.05)
    ext_rel0.test(cycles=3, on_time=0.05, off_time=0.05)
    cur = ACS71240(viout_pin=HAL.ADC_CURRENT_BAT_PIN, fault_pin=HAL.CURRENT_FAULT_PIN)
    cur.calibrate_zero()
    spi = SoftSPI(baudrate=1000000, polarity=0, phase=0, sck=Pin(HAL.SPI_SCLK_PIN), mosi=Pin(HAL.SPI_MOSI_PIN), miso=Pin(HAL.SPI_MISO_PIN))
    vol = ADS1118(spi=spi, cs_pin = HAL.SPI_CS_PIN, channel_mux={0: 0b000, 1: 0b011}, gain=[1.0, 1.0]) #channel 0 = Bat, channel 1 = inv
    tmp = DS18B20(data_pin=HAL.OWM_TEMP_PIN, pullup=False)
    soc_estimator = BatterySOC(soc_config)
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
        #TODO: this chan be put in a method/class e.g. master measurements handler
        slave_handler.request_all_data()
        meas.current = cur.read_current(samples=10)
        log.info(f"Current: {meas.current} A")
        meas.vpack = await vol.read_voltage(channel=0)
        meas.vinv = await vol.read_voltage(channel=1)
        meas.tadc = await vol.read_temperature()
        log.info(f"Battery Voltage: {meas.vpack}, Inverter Voltage: {meas.vinv}, ADC Temp: {meas.tadc}")
        meas.tpack = tmp.get_temperatures()[1]
        log.info(f"Temperatures: {meas.tpack}")
        soc = max(0, int(round(await soc_estimator.update(meas.current, meas.vpack, meas.tpack))))
        log.info(f"Estimated SOC: {soc} %")

        #TODO: implement FSM!!!!!!!
        #protector starts checks
        protector.start(slaves=slave_handler.slaves, data = meas)
        
        protector.connect_to_inv() #this only triggers if protection ready.
        #can_bus.send_status(prot_status)
        for s in slave_handler.slaves:
            log.info(f"Voltages: {s.battery.meas.vcell}")
        await asyncio.sleep(5)

# ----------------------------------------------------------------------
#  Boot
# ----------------------------------------------------------------------
try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Stopped by user")