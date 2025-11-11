# slave.py
import network, espnow, time, binascii
import json
import asyncio
from machine import RTC
from common.common import *


# -------------------------------------------------
# 1. Configuration
# -------------------------------------------------
MASTER_MAC = b'\x24\x0a\xc4\xAA\xBB\xCC'   # <-- replace
SYNC_TIMEOUT = 10_000_000                 # 10 s without sync → drift warning

# -------------------------------------------------
# 2. Init
# -------------------------------------------------
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.config(channel=1)

e = espnow.ESPNow()
e.active(True)
e.add_peer(MASTER_MAC)

rtc = RTC()
rtc.datetime((2025, 1, 1, 3, 0, 0, 0, 0))   # arbitrary start

# Offset storage (microseconds)
offset_us = 0
last_sync = time.ticks_us()
print("Slave ready – MAC:", binascii.hexlify(wlan.config('mac'), ':'))

# -------------------------------------------------
# 3. Helper: apply offset to RTC
# -------------------------------------------------
def apply_offset():
    """Add offset_us to the RTC (sub-second only)."""
    dt = list(rtc.datetime())
    # subsec is in µs (0-999999)
    subsec = dt[7] + offset_us
    seconds_carry = subsec // 1_000_000
    dt[7] = subsec % 1_000_000
    # carry over seconds → minutes → etc.
    secs = dt[6] + seconds_carry
    mins_carry = secs // 60
    dt[6] = secs % 60
    hrs_carry = (dt[5] + mins_carry) // 60
    dt[5] = (dt[5] + mins_carry) % 60
    # (ignore day/month/year carry for simplicity – offset is tiny)
    rtc.datetime(tuple(dt))

# ========================================
# Listen to master
# ========================================
def listener(e):
    while True:
        mac, msg = e.irecv(0)
        if mac is None:
            return
        if msg:
            # Deserialize JSON
            dict = json.loads(msg)
            # Check message type
            msg_type = dict.get("type")
            # Handle Welcom message
            if msg_type == WELCOME_MSG:
                # TODO: if state == DISCOVER change state to SYNC_WAIT
                pass
            
            # Handle Sync request message
            if msg_type == SYNC_REQ_MSG:
                T1 = unpack_sync_req(msg)
                T2 = time.ticks_us()
                e.send(MASTER_MAC, pack_sync_ack(T1, T2))
                # TODO: change state to SYNC_ACK

            
            # Handle Sync ref message
            if msg_type == SYNC_REF_MSG:
                pass


# -------------------------------------------------
# Main
# -------------------------------------------------
async def main():
    e.irq(listener)
    state = "INIT"
    if state == "INIT":
        pass
    elif state == "DISCOVER":
        e.send()


    T1 = T2 = T3 = T4 = None
    while True:
        host, msg = e.recv(100)                 # 100 ms timeout
        now = time.ticks_us()

        # ---- 1. Sync Request (T1) ----
        if state == "WAIT_SYNC" and msg and len(msg) == struct.calcsize(SYNC_REQ_FMT):
            seq, T1 = unpack_sync_req(msg)
            T2 = now
            # send ACK immediately
            e.send(MASTER_MAC, pack_ack(T1, T2))
            state = "WAIT_REF"
            print(f"SyncReq seq={seq} T1={T1} T2={T2}")

        # ---- 2. Reference (T1,T2,T3) ----
        elif state == "WAIT_REF" and msg and len(msg) == struct.calcsize(REF_FMT):
            T1_rcv, T2_rcv, T3 = unpack_ref(msg)
            if T1_rcv == T1 and T2_rcv == T2:      # sanity check
                T4 = now
                # ---- NTP calculation ----
                rtt = time.ticks_diff(T4, T1) - time.ticks_diff(T3, T2)
                offset = (time.ticks_diff(T2, T1) + time.ticks_diff(T3, T4)) // 2
                # store
                offset_us = offset
                apply_offset()
                last_sync = now
                print(f"NTP sync: offset={offset_us}µs  RTT={rtt}µs")
                state = "WAIT_SYNC"
            else:
                print("REF mismatch – discard")
                state = "WAIT_SYNC"

        # ---- watchdog – warn if no sync for a while ----
        if time.ticks_diff(now, last_sync) > SYNC_TIMEOUT:
            print("WARNING: no sync for >10 s")
            last_sync = now   # avoid spamming



# Run the async loop
asyncio.run(main())


#######################################################################
## Main
#######################################################################
from machine import Pin, SoftSPI, SoftI2C
from SN74HC154 import SN74HC154
from ADS1118 import ADS1118
from PCA9685 import PCA9685
from DS18B20 import DS18B20
import asyncio

SLAVE_MAX = True

if SLAVE_MAX :
    NR_OF_ADCS = 12
    NR_OF_PCA = 2
else:
    NR_OF_ADCS = 6
    NR_OF_PCA = 1

#Initialize DS18B20 temperature sensors
temp_sens = DS18B20(pin_num=5)  # GPIO5 for


# Initialize I2C for PCA9685
i2c = SoftI2C(scl=Pin(9), sda=Pin(8), freq=400000)  # I2C0, 400 kHz

# Initialize SPI for ADS1118
spi = SoftSPI(
    baudrate=1000000,
    polarity=0,
    phase=0,
    sck=Pin(10),
    mosi=Pin(11),
    miso=Pin(12),
)

# Initialize SN74HC154 demultiplexer (GPIO pins 0, 1, 2, 3 for A0-A3, enable on GP4)
demux = SN74HC154(enable_pin=4, a0_pin=0, a1_pin=1, a2_pin=2, a3_pin=3)

# Initialize PCA9685
pcas = [PCA9685(i2c, address=0x40 + i) for i in range(NR_OF_PCA)]
for pca in pcas:
    pca.set_pwm_freq(100)  # 100 Hz PWM

# Initialize ADS1118 instances
mux = {0: 0b000, 1: 0b010, 2: 0b011}
adcs = []

adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x1, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x2, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x3, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x4, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x5, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x6, pga=2, dr=4, channel_mux={0: 0b000, 1: 0b011}, gain=[1.0, 1.0]))
if SLAVE_MAX :
    adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0xF, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0xE, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0xD, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0xC, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0xB, pga=2, dr=4, channel_mux=mux, gain=[1.0, 1.0, 1.0]))
    adcs.append(ADS1118(spi=spi, demux=demux, demux_output=0x0, pga=2, dr=4, channel_mux={0: 0b000, 1: 0b011}, gain=[1.0, 1.0]))


async def read_all_adc():
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

async def main():
    odd_mask  = [1] * 16
    even_mask = [1] * 16
    # Optional: Calibrate all ADCs once at startup (assuming inputs shorted)
    #for adc in adcs:
    #    await adc.calibrate(0)
    #    await adc.calibrate(1)

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

        # Read voltages
        voltages = await read_all_adc()
        cell_voltages_1 = voltages[0:15]
        string_voltage_1 = voltages[16]
        if SLAVE_MAX :
            cell_voltages_2 = voltages[17:32]
            string_voltage_2 = voltages[33]
        # Read temperatures DS18B20
        temperatures = temp_sens.get_temperatures()

        # Transfer data to master

        # Receive commands from master
        bal_ch = [1,3,5,6,7,9,22,31] # balancing command from master

        for ch in bal_ch:
            if ch <= 15:
                    pcas[0].set_duty(ch, 50)
            else:
                    pcas[1].set_duty(ch, 50)
            

        # Check for over temperature TODO: replace magic numbers with config from master
        for t in temperatures.values():
            if t >= 60.0:
                print("Over Temperature detected!")
        # Cross check sum of cell voltages with string voltage --> aproximation TODO: replace magic numbers with config from master
        sum_cell_voltages_1 = sum([v for v in cell_voltages_1 if v is not None])
        if abs(sum_cell_voltages_1 - string_voltage_1) > 2.0:
            print("Voltage mismatch in string 1!")
        if SLAVE_MAX:
            sum_cell_voltages_2 = sum([v for v in cell_voltages_2 if v is not None])
            if abs(sum_cell_voltages_2 - string_voltage_2) > 2.0:
                print("Voltage mismatch in string 2!")
        # Check for String OV,UV TODO: replace magic numbers with config from master
        if string_voltage_1 is not None:
            if string_voltage_1 >= 57.6: 
                print("Over Voltage detected in string 1!")
            elif string_voltage_1 <= 41.6:
                print("Under Voltage detected in string 1!")
        # Check for OV=3.6V UV=2.6V TODO: replace magic numbers with config from master
        for i, v in enumerate(cell_voltages_1): 
            if v is not None:
                if v >= 3.6:
                    print(f"Over Voltage detected in string 1, cell {i}!")
                elif v <= 2.6:
                    print(f"Under Voltage detected in string 1, cell {i}!")
        # build odd_mask bal_th = 3.4V ,bal_diff_th = 0.2V
        for i, v in enumerate(cell_voltages_1): 
            if v is not None:
                if v >= 3.4:
                    odd_mask[i*2+1] = 1
                elif v <= 3.2:
                    odd_mask[i*2+1] = 0
        # build even_mask bal_th = 3.4V ,bal_diff_th = 0.2V


# Run the async loop
asyncio.run(main())
