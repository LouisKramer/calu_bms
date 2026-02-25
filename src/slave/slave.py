# slave.py
import time, machine, random
from machine import Pin, SoftSPI, SoftI2C, RTC
from common.HAL import slave_hal as HAL
import asyncio
from common.logger import Logger
from common.common import *
from common.credentials import *
Logger.init(syslog_host=SYSLOG_HOST)
from lib.SN74HC154 import SN74HC154
#from lib.ADS1118 import *
from lib.ADS1118_V2 import ADS1118
from lib.PCA9685 import *
from lib.DS18B20 import *
from lib.BMSnow import BMSnowSlave
from lib.BMSadc import BMSadc
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
# ========================================
# INIT
# ========================================
time.sleep(2)
log = Logger()
log.info("Init System")

str_sel0 = Pin(HAL.STR_SEL0_PIN, Pin.IN, pull = Pin.PULL_DOWN) 
str_sel1 = Pin(HAL.STR_SEL1_PIN, Pin.IN, pull = Pin.PULL_DOWN)
str_sel2 = Pin(HAL.STR_SEL2_PIN, Pin.IN, pull = Pin.PULL_DOWN)
str_sel3 = Pin(HAL.STR_SEL3_PIN, Pin.IN, pull = Pin.PULL_DOWN)
# ========================================
# MAIN
# ========================================
async def main():
    log.info("Starting main application...")
    bat = battery()
    bat.info.mac = machine.unique_id()
    bat.info.addr = read_string_address()# TODO: optionally if addrs == 0xF do calibration or some special mode
    log.info(f"String address set to {bat.info.addr}")
    tmp = DS18B20(data_pin=HAL.OWM_TEMP_PIN, pullup=False)
    i2c = SoftI2C(scl=Pin(HAL.I2C_SCL_PIN, pull=Pin.PULL_UP), sda=Pin(HAL.I2C_SDA_PIN, pull=Pin.PULL_UP), freq=400000)
    spi = SoftSPI(baudrate=1000000, polarity=0, phase=0, sck=Pin(HAL.SPI_SCLK_PIN), mosi=Pin(HAL.SPI_MOSI_PIN), miso=Pin(HAL.SPI_MISO_PIN))
    adc = BMSadc(spi)
    await adc.start_all_continuous_scans()
    adc.start_adc_task(bat,interval_ms=120)

    bat.info.ntemp = tmp.number_of_sensors()
    bat.info.ncell = bat.meas.get_nr_of_cells() # Place Holder
    bat.info.fw_ver = FW_VERSION
    bat.info.fw_ver = HW_VERSION

    # Initialize PCA9685
    #pca1=PCA9685(i2c, address=0x40)
    #pca1.set_pwm_freq(BAL_PWM_FREQ)  # 100 Hz PWM
    pca = PCA9685(i2c)
    pca.freq(BAL_PWM_FREQ)

    #pca1.all_off()

    #pcas = [PCA9685(i2c, address=0x40 + i) for i in range(NR_OF_PCA)]
    #for pca in pcas:
    #    pca.set_pwm_freq(BAL_PWM_FREQ)  # 100 Hz PWM
    #    pca.all_off()
            
    # We are ready to show ourselves to the master
    slave = BMSnowSlave(bat)
    await slave.start()
    log.info("main loop")
    while True:
        log.info(f"Cell Voltages {bat.meas.vcell}")
        log.info(f"String Voltage: {bat.meas.vstr}")

        temps = tmp.get_temperatures()
        temps[0] = 33.3
        bat.meas.temps = [temps[0]]
        log.info(f"Temperatures: {temps}")

        ## Balancing
        for i in range(NR_OF_CELLS):
            pca.duty(i, 0) #channel i, on=0, off=2048 (50% duty cycle)

        await asyncio.sleep(1)

def read_string_address():
    """Read 4-bit address from GPIO pins (0-15)"""
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




