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
    bat.info.addr = read_string_address()
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

    even_odd_flag = False
    while True:
        log.info("main loop")
        bat.meas.vcell = [round(random.uniform(3.0, 4.2), 3) for _ in range(bat.info.ncell)]
        bat.meas.vstr = 48.5
        # Read voltages
        #voltages = await read_all_adc(adcs=adcs)
        #demux.select(0x0)
        b1 = await bat1_3.read_voltage(channel=0)
        b2 = await bat1_3.read_voltage(channel=1)
        b3 = await bat1_3.read_voltage(channel=2)

        b4 = await bat4_6.read_voltage(channel=0)
        b5 = await bat4_6.read_voltage(channel=1)
        b6 = await bat4_6.read_voltage(channel=2)

        b7 = await bat7_9.read_voltage(channel=0)
        b8 = await bat7_9.read_voltage(channel=1)
        b9 = await bat7_9.read_voltage(channel=2)

        b10 = await bat10_12.read_voltage(channel=0)
        b11 = await bat10_12.read_voltage(channel=1)
        b12 = await bat10_12.read_voltage(channel=2)

        b13 = await bat13_15.read_voltage(channel=0)
        b14 = await bat13_15.read_voltage(channel=1)
        b15 = await bat13_15.read_voltage(channel=2)

        b16 = await bat16.read_voltage(channel=0)
        #demux.deselect()
        log.info(f"Cell Voltages: {b1}, {b2}, {b3}")
        log.info(f"Cell Voltages: {b4}, {b5}, {b6}")
        log.info(f"Cell Voltages: {b7}, {b8}, {b9}")
        log.info(f"Cell Voltages: {b10}, {b11}, {b12}")
        log.info(f"Cell Voltages: {b13}, {b14}, {b15}")
        log.info(f"Cell Voltage: {b16}")
        #cell_voltages_1 = voltages[0:15]
        #string_voltage_1 = voltages[16]
        #if SLAVE_MAX :
        #    cell_voltages_2 = voltages[17:32]
        #    string_voltage_2 = voltages[33]
        temps = tmp.get_temperatures()
        temps[0] = 33.3
        bat.meas.temps = [temps[0]]
        log.info(f"Temperatures: {temps}")

        ## Balancing
        for i in range(NR_OF_CELLS):
            pca.duty(i, 0) #channel i, on=0, off=2048 (50% duty cycle)

        ## TODO: odd and even Balancing must be synced over all slaves!!!!!!
        #even_odd_flag = not even_odd_flag
        #if bal_en == True and ext_bal_en == False:
        #    for i, v in enumerate(voltages[cell_voltages_1]): 
        #        if v is not None:
        #            if v >= bal_start_voltage:
        #                pcas[0].set_duty(i, 50)
        #            elif v <= bal_start_voltage - bal_threshold:
        #                pcas[0].off(i)
        #    await asyncio.sleep(0.3)
        #    for i, v in enumerate(voltages[cell_voltages_2]): 
        #        if v is not None:
        #            if v >= bal_start_voltage:
        #                pcas[1].set_duty(i, 50)
        #            elif v <= bal_start_voltage - bal_threshold:
        #                pcas[1].off(i)
        #    for pca in pcas:
        #        pca.all_off()
        await asyncio.sleep(1)

async def read_all_adc(adcs):
    """
    Asynchronously reads all ADC channels from all ADS1118 instances and returns their voltages as a list.
    """
    num_adcs = len(adcs)
    total_channels = 0
    max_channels = 0
    for adc in adcs:
        total_channels = total_channels + adc.nr_of_ch
        max_channels = adc.nr_of_ch if adc.nr_of_ch > max_channels else max_channels
    vol = [0] * total_channels
    
    # Initialize pipeline
    for adc in adcs:
        try:
            await adc.start_conversions_all(channel=0, ret=False)
        except Exception as e:
            print(f"Error initializing ADC: {e}")

    # Read all channels
    for j in range(max_channels):
        prev_nr_of_ch = 0
        for i, adc in enumerate(adcs):
            if j <= adc.nr_of_ch - 1:
                try:
                    vol[j + i * prev_nr_of_ch] = await adc.start_conversions_all(channel=j, ret=True)
                except Exception as e:
                    print(f"Error reading ADC {i} channel {j}: {e}")
                    vol[j + i * prev_nr_of_ch] = None
            else:
                pass
            prev_nr_of_ch = adc.nr_of_ch

        #wait to complete conversion.
        # SPI @1MHz and 2 bytes takes adc_read_time = ~100us (16us for 2 bytes, rest overhead)
        # @ 128 SPS every ~8ms a new value
        # --> one round trip should at least last: 10ms
        # whitout delay: nr_of_adcs * adc_read_time
        await asyncio.sleep(adc.get_conversion_delay() - (num_adcs * 0.0001))
    # total roundtrip time = num_channels * (conversion_delay - (nr_of_adcs * adc_read_time))
    # trt = ~70ms
    return vol

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

asyncio.run(main())




