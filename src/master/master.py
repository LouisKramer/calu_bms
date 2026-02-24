# master.py
import time
import asyncio
from common.HAL import master_hal as HAL
from machine import SoftSPI
from common.credentials import *
from common.common import *
from common.logger import *
from lib.ACS71240 import *
from lib.ADS1118_V2 import ADS1118
from lib.DS18B20 import *
from lib.RELAY import *
from lib.SOC import BatterySOC, autosave_task
from lib.NTP import *
from lib.virt_slave import *
from lib.BMSnow import BMSnowMaster
from lib.WLAN import WlanManager
#from lib.CAN import * Wait for support in micropython-esp32
from lib.PROT import Protector
from lib.Power_manager import PowerManager
from lib.BMSmqtt import get_BMSmqtt

# ========================================
# Config
# ========================================
MQTT_ENABLE = False
Logger.init(syslog_host=SYSLOG_HOST)
cfg = init_config()
cfg_bms  = bms_config()
cfg_prot = protection_config()
cfg_soc  = soc_config()
cfg_pow  = power_config()
cfg_can  = can_config()
# ========================================
# MAIN
# ========================================
async def main():
    time.sleep(3)
    log = Logger()

    log.info("Starting wifi manager")
    wifi = WlanManager(ssid=WIFI_SSID, password=WIFI_PASS, hostname=WIFI_HOST, led_pin=HAL.LED_USER_PIN)
    wifi.start()
    while not wifi.is_connected():
        print("Waiting for WiFi connection...")
        await asyncio.sleep(1)
    log.info("WiFi connected")

    log.info("Start NTP client")
    ntp = ntp_sync(NTP_HOST, NTP_PORT, NTP_TIMEOUT, NTP_SYNC_INTERVAL)
    asyncio.create_task(ntp.ntp_task())

    if MQTT_ENABLE:
        log.info("Start mqtt client")
        mqtt = get_BMSmqtt()
        asyncio.create_task(mqtt.run())

    log.info("Init Protection")
    protector = Protector(cfg_prot)
    if MQTT_ENABLE:
        cfg_prot.init_mqtt_entities()

    log.info("Init SoC estimator")
    soc_estimator = BatterySOC(cfg_soc)
    if MQTT_ENABLE:
        cfg_soc.init_mqtt_entities()
    asyncio.create_task(soc_estimator.autosave_task(interval=60))

    log.info("Init Power Manager")
    pow_manager = PowerManager(cfg=cfg_pow)
    if MQTT_ENABLE:
        cfg_pow.init_mqtt_entities()

    log.info("Start BMSnow Master AP")
    meas = master_data()
    if MQTT_ENABLE:
        meas.init_mqtt_entities()
    slave_handler = BMSnowMaster()
    slave_handler.start()    

    log.info("Init CAN")    
    #can= BMSCan(cfg_can)

    #int_rel0 = Relay(pin=HAL.INT_REL0_PIN, active_high=True)
    #int_rel1 = Relay(pin=HAL.INT_REL1_PIN, active_high=True)
    #ext_rel0 = Relay(pin=HAL.EXT_REL0_PIN, active_high=True)
    #int_rel0.test(cycles=3, on_time=0.05, off_time=0.05)
    #int_rel1.test(cycles=3, on_time=0.05, off_time=0.05)
    #ext_rel0.test(cycles=3, on_time=0.05, off_time=0.05)

    log.info("Init Current Sensor")
    cur = ACS71240(viout_pin=HAL.ADC_CURRENT_BAT_PIN, fault_pin=HAL.CURRENT_FAULT_PIN)
    cur.calibrate_zero()

    log.info("Init Voltage Sensor")
    spi = SoftSPI(baudrate=1000000, polarity=0, phase=0, sck=Pin(HAL.SPI_SCLK_PIN), mosi=Pin(HAL.SPI_MOSI_PIN), miso=Pin(HAL.SPI_MISO_PIN))
    vol = ADS1118(spi=spi, cs_pin= HAL.SPI_CS_PIN)

    #vol = ADS1118(spi=spi, cs_pin = HAL.SPI_CS_PIN, channel_mux={0: 0b000, 1: 0b011},  soft_gain=[249.0, 249.0]) #channel 0 = Bat, channel 1 = inv
    
    log.info("Init Temperature Sensor")
    tmp = DS18B20(data_pin=HAL.OWM_TEMP_PIN, pullup=False)
    
    state = "discover slaves"
    log.info("Initialization complete, entering main loop.")
    while True:
        #TODO: this chan be put in a method/class e.g. master measurements handler
        slave_handler.request_all_data()
        meas.update_current(cur.read_current(samples=10))
        meas.update_vpack(await vol.read(mux = ADS1118.MUX_AIN0_AIN1, gain = 249.0))
        meas.update_vinv(await vol.read(mux = ADS1118.MUX_AIN2_AIN3, gain = 249.0))
        meas.update_tadc(await vol.read_temperature())
        meas.update_tpack(0)#tmp.get_temperatures())
        soc, soh, cycles = soc_estimator.update(meas.current, meas.vpack, meas.tpack, slave_handler.slaves.nr_of_cells())
        meas.update_soc(soc)
        meas.update_soh(soh)
        meas.update_cycle_cnt(cycles)
        log.info(f"Battery Voltage: {meas.vpack}, Inverter Voltage: {meas.vinv}, ADC Temp: {meas.tadc}")
        log.info(f"Current: {meas.current} A")
        log.info(f"Temperatures: {meas.tpack}")

        #TODO: implement FSM!!!!!!!
        #protector starts checks
        if state == "discover slaves":
            #wait for some time to discover slaves and get initial data
            if len(slave_handler.slaves) > 0: #TODO: define expected number of slaves.
                log.info(f"Discovered {len(slave_handler.slaves)} slaves with total {slave_handler.slaves.nr_of_cells()} cells")
                state = "wait for stable measurements"
            else:
                log.warn("No slaves discovered yet")
        elif state == "wait for stable measurements":
            #wait for measurements to stabilize
            if all(s.battery.state.stable for s in slave_handler.slaves):
                log.info("Measurements stabilized, ready to connect to inverter")
                state = "start protection"
            else:
                log.info("Waiting for stable measurements from all slaves")
        elif state == "start protection":
            if protector.start(slaves=slave_handler.slaves, data = meas)==True:
                log.info("Protection started successfully")
                state = "connect to inverter"
        elif state == "connect to inverter":
            if await protector.connect_to_inv() == True:
                log.info("Connected to inverter, entering normal operation")
                state = "normal operation"
        elif state == "normal operation":
            charge_current, discharge_current = pow_manager.update(soc)
            log.info(f"Allowed charge current: {charge_current:.2f} A, discharge current: {discharge_current:.2f} A")


        #can_bus.send_status(prot_status)
        
        for s in slave_handler.slaves:
            log.info(f"Voltages: {s.battery.meas.vcell}")
            log.info(f"Temperatures: {s.battery.meas.temps}")
            log.info(f"String Voltage: {s.battery.meas.vstr}")
        await asyncio.sleep(2)

# ----------------------------------------------------------------------
#  Boot
# ----------------------------------------------------------------------
try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Stopped by user")