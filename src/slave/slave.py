# slave.py
import time, machine, random
from machine import Pin, SoftSPI, SoftI2C, RTC
from common.HAL import slave_hal as HAL
import asyncio
from common.logger import Logger
from common.common import battery
from common.credentials import *

from lib.PCA9685 import *
from lib.DS18B20 import *
from lib.BMSnow import BMSnowSlave
from lib.BMSadc import BMSadc
from lib.BMSbal import BMSbal
# ========================================
# CONFIG
# ========================================
BAL_PWM_FREQ = 1600  # Hz

FW_VERSION = "0.0.0.1"
HW_VERSION = "2.0.0.0"

SLAVE_MAX = True

if SLAVE_MAX :
    NR_OF_ADCS = 12
    NR_OF_PCA = 2
    NR_OF_CELLS = 32
else:
    NR_OF_ADCS = 6
    NR_OF_PCA = 1
    NR_OF_CELLS = 16
Logger.init(syslog_host=SYSLOG_HOST)
# ========================================
# MAIN
# ========================================
async def main():
    time.sleep(3)
    log = Logger()
    log.info("Init dataset")
    bat = battery()
    bat.info.fw_ver = FW_VERSION
    bat.info.fw_ver = HW_VERSION
    bat.info.mac = machine.unique_id()
    bat.info.addr = read_string_address()# TODO: optionally if addrs == 0xF do calibration or some special mode
    log.info(f"Read address : {bat.info.addr}")

    log.info("Init temp sensors")
    tmp = DS18B20(data_pin=HAL.OWM_TEMP_PIN, pullup=False)
    if tmp.number_of_sensors() <= 0:
        log.warn("No Tempsensor found!")
    else:
        log.info(f"Found {tmp.number_of_sensors()} temp sensors")
        bat.info.ntemp = tmp.number_of_sensors()

    log.info("Init i2c")
    i2c = SoftI2C(scl=Pin(HAL.I2C_SCL_PIN, pull=Pin.PULL_UP), sda=Pin(HAL.I2C_SDA_PIN, pull=Pin.PULL_UP), freq=400000)

    log.info("Init spi")
    spi = SoftSPI(baudrate=1000000, polarity=0, phase=0, sck=Pin(HAL.SPI_SCLK_PIN), mosi=Pin(HAL.SPI_MOSI_PIN), miso=Pin(HAL.SPI_MISO_PIN))
    
    log.info("Init adc")
    adc = BMSadc(spi)
    log.info("Start ADC continous scan")
    await adc.start_all_continuous_scans()
    log.info("Start ACD data aquisition task")
    adc.start_adc_task(bat,interval_ms=500)
    log.info("Wait 5s for ADC settling")
    for i in range(5):
        log.info(f"{i}s")
        await asyncio.sleep(1)
    bat.info.ncell = bat.meas.get_nr_of_cells() # Place Holder

    log.info("Init Balancing")
    # Initialize PCA9685
    pca1=PCA9685(i2c, address=0x40)
    #pca2=PCA9685(i2c, address=0x41)
    bal = BMSbal([pca1])
    await bal.start(phase_duration_ms=250)
    bal.enable_auto(bat=bat)
            
    log.info("Init BMS Slave")
    slave = BMSnowSlave(bat)
    await slave.start()

    log.info("Init done, enter main loop")
    while True:
        log.info(f"Cell Voltages {bat.meas.vcell}")
        log.info(f"String Voltage: {bat.meas.vstr}")

        temps = tmp.get_temperatures()
        temps[0] = 33.3
        bat.meas.temps = [temps[0]]
        log.info(f"Temperatures: {temps}")

        await asyncio.sleep(1)

def read_string_address():
    """Read 4-bit address from GPIO pins (0-15)"""
    str_sel0 = Pin(HAL.STR_SEL0_PIN, Pin.IN, pull = Pin.PULL_DOWN) 
    str_sel1 = Pin(HAL.STR_SEL1_PIN, Pin.IN, pull = Pin.PULL_DOWN)
    str_sel2 = Pin(HAL.STR_SEL2_PIN, Pin.IN, pull = Pin.PULL_DOWN)
    str_sel3 = Pin(HAL.STR_SEL3_PIN, Pin.IN, pull = Pin.PULL_DOWN)
    addr = 0
    addr |= (str_sel0.value() << 0)
    addr |= (str_sel1.value() << 1)
    addr |= (str_sel2.value() << 2)
    addr |= (str_sel3.value() << 3)
    # Optional: clamp to valid range (in case of noise)
    if addr > 15:
        addr = 0  # or raise an error, or return None, depending on your needs
    return addr

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Stopped by user")




