# slave.py
import network, espnow, time, machine
from machine import Pin, SoftSPI, SoftI2C, RTC
import asyncio
from common.logger import Logger
from common.common import *
from common.credentials import *
Logger.init(syslog_host=SYSLOG_HOST)
from lib.SN74HC154 import SN74HC154
from lib.ADS1118 import *
from lib.PCA9685 import *
from lib.DS18B20 import *
from lib.BMSnow import BMSnowSlave
# ========================================
# CONFIG
# ========================================
SPI_CS_STR0_PIN = 4
SPI_CS_STR1_PIN = 5
SPI_SCLK_PIN = 6
SPI_MOSI_PIN = 7
SPI_MISO_PIN = 15
SPI_CS0_PIN = 16
SPI_CS1_PIN = 17
SPI_CS2_PIN = 18
SPI_CS3_PIN = 8
I2C_SCL_PIN = 46
I2C_SDA_PIN = 3
OWM_TEMP_PIN = 9
CS_EN_PIN = 10
ACT_BAL_PIN = 47
ACT_BAL_PWM_PIN = 48
LED_USER_PIN = 40
LED_ERR_PIN = 39
STR_SEL0_PIN = 41
STR_SEL1_PIN = 42
STR_SEL2_PIN = 2
STR_SEL3_PIN = 38

BAL_PWM_FREQ = 100  # Hz

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
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
#TODO: check for updates
wlan.config(channel=11)
wlan.disconnect()
print(f"Wlan channel: {wlan.config('channel')}")

#str_sel0 = Pin(STR_SEL0_PIN, Pin.IN, pull = Pin.PULL_DOWN) 
#str_sel1 = Pin(STR_SEL1_PIN, Pin.IN, pull = Pin.PULL_DOWN)
#str_sel2 = Pin(STR_SEL2_PIN, Pin.IN, pull = Pin.PULL_DOWN)
#str_sel3 = Pin(STR_SEL3_PIN, Pin.IN, pull = Pin.PULL_DOWN)
# ========================================
# MAIN
# ========================================
async def main():
    log.info("Starting main application...")
    bat = battery()
    bat.info.mac = machine.unique_id()
    bat.info.addr = 2#read_string_address()
    log.info(f"String address set to {bat.info.addr}")
    tmp = DS18B20(data_pin=OWM_TEMP_PIN, pullup=False)
    bat.info.ntemp = tmp.number_of_sensors()
    bat.info.ncell = 32 # Place Holder
    bat.info.fw_ver = FW_VERSION
    bat.info.fw_ver = HW_VERSION
    bat.create_measurements()

    #i2c = SoftI2C(scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=400000)
    #spi = SoftSPI(baudrate=1000000, polarity=0, phase=0, sck=Pin(SPI_SCLK_PIN), mosi=Pin(SPI_MOSI_PIN), miso=Pin(SPI_MISO_PIN))
    #demux = SN74HC154(enable_pin=CS_EN_PIN, a0_pin=SPI_CS0_PIN, a1_pin=SPI_CS1_PIN, a2_pin=SPI_CS2_PIN, a3_pin=SPI_CS3_PIN)
    # Initialize PCA9685
    #pcas = [PCA9685(i2c, address=0x40 + i) for i in range(NR_OF_PCA)]
    #for pca in pcas:
    #    pca.set_pwm_freq(BAL_PWM_FREQ)  # 100 Hz PWM
    #    pca.all_off()

    # Initialize ADS1118 instances
    #mux = {0: 0b000, 1: 0b010, 2: 0b011}
    #adcs = []#
#
    #adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x1, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    #adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x2, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    #adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x3, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    #adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x4, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    #adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x5, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    #adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x6, pga=2, dr=4, channel_mux={0: 0b000, 1: 0b011}, gain=[1.0, 1.0]))
    #if SLAVE_MAX :
    #    adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0xF, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    #    adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0xE, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    #    adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0xD, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    #    adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0xC, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    #    adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0xB, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    #    adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x0, pga=2, dr=4, channel_mux={0: 0b000, 1: 0b011}, gain=[1.0, 1.0]))
    
    # Optional: Calibrate all ADCs once at startup (assuming inputs shorted)
    #if str_addr == 0:
    #    log.info(f"Calibrating ADCs...", ctx="boot")
    #    for adc in adcs:
    #        for ch in range(adc.nr_of_ch):
    #            await adc.calibrate(ch)
    #    log.info(f"ADC Calibration complete.", ctx="boot")
    #    while True:
    #        log.info("Calibration done. Slave in standby mode for address 0. Set address via STR_SEL pins and restart.", ctx="boot")
    #        await asyncio.sleep(10)
            
    # We are ready to show ourselves to the master
    slave = BMSnowSlave(bat)
    await slave.start()

    even_odd_flag = False
    while True:
        log.info("main loop")
        # Read voltages
        #voltages = await read_all_adc()
        #log.info(f"Cell Voltages: {voltages}", ctx="main")
        #cell_voltages_1 = voltages[0:15]
        #string_voltage_1 = voltages[16]
        #if SLAVE_MAX :
        #    cell_voltages_2 = voltages[17:32]
        #    string_voltage_2 = voltages[33]
        #temps = tmp.get_temperatures()
        #log.info(f"Temperatures: {temps}", ctx="main")

        ## Balancing
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
        await asyncio.sleep(10)

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



async def main2():
    odd_mask  = [1] * 16
    even_mask = [1] * 16
    # TODO: odd and even Balancing must be synced over all slaves!!!!!!
    while True: 
        # Enable odd PCA9685 channel Balancing (1, 3, ..., 15)
        for pca in pcas:
            pca.enable_odd_channels(50, mask=odd_mask)
        await asyncio.sleep(0.3)
        # Enable even PCA9685 channel Balancing (0, 2, ..., 14)
        for pca in pcas:
            pca.enable_even_channels(50, mask=even_mask)
        await asyncio.sleep(0.3)

        for i, v in enumerate(cell_voltages_1): 
            if v is not None:
                if v >= 3.4:
                    odd_mask[i*2+1] = 1
                elif v <= 3.2:
                    odd_mask[i*2+1] = 0
        # build even_mask bal_th = 3.4V ,bal_diff_th = 0.2V


