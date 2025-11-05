# master.py
import network, espnow, time, binascii, socket, struct
from machine import RTC
from common.common import *
import asyncio
import json

# ========================================
# CONFIG
# ========================================
WIFI_SSID = "YOUR_SSID"
WIFI_PASS = "YOUR_PASSWORD"

NTP_HOST = "pool.ntp.org"
NTP_PORT = 123
NTP_TIMEOUT = 5  # seconds

NTP_SYNC_INTERVAL = 3600
SLAVE_SYNC_INTERVAL = 10
SLAVE_TTL = 3600

# ========================================
# INIT
# ========================================
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.config(channel=1)

# Connect to Wi-Fi
print("Connecting to Wi-Fi...")
wlan.connect(WIFI_SSID, WIFI_PASS)
while not wlan.isconnected():
    time.sleep(0.5)
print("Wi-Fi connected. IP:", wlan.ifconfig()[0])

# ESP-NOW
e = espnow.ESPNow()
e.active(True)

rtc = RTC()
# ========================================
# NTP CLIENT (get real time)
# ========================================
async def sync_with_ntp():
    print("Syncing with NTP server...")
    ntp_packet = bytearray(48)
    ntp_packet[0] = 0x1B  # LI=0, VN=3, Mode=3 (client)

    addr = socket.getaddrinfo(NTP_HOST, NTP_PORT)[0][-1]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(NTP_TIMEOUT)
    try:
        s.sendto(ntp_packet, addr)
        # Use asyncio.sleep to allow other tasks to run while waiting
        await asyncio.sleep(0.1)
        msg, _ = s.recvfrom(48)
        # NTP timestamp is at offset 40 (seconds since 1900)
        ntp_time = struct.unpack("!I", msg[40:44])[0]
        # Convert to Unix epoch (1970)
        epoch = ntp_time - 2208988800
        # Set RTC
        tm = time.gmtime(epoch)
        # MicroPython RTC expects weekday in range 1-7 (Monday=1), utime.gmtime gives 0-6 (Monday=0)
        rtc.datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
        print("RTC set to UTC:", rtc.datetime())
    except Exception as ex:
        print("NTP sync failed: using default fallback (2024-01-01)", ex)
        fallback_epoch = 1704067200
        tm = time.gmtime(fallback_epoch)
        rtc.datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
        print("RTC set to fallback UTC:", rtc.datetime())
        return False
    finally:
        s.close()

async def ntp_task():
    while True:
        await sync_with_ntp()
        await asyncio.sleep(NTP_SYNC_INTERVAL)

# ========================================
# Class representing a slave 
# ========================================
class Slaves:
    MAX_NR_OF_SLAVES = 16
    def __init__(self):
        # init max number of slaves
        self.slaves = [None]*self.MAX_NR_OF_SLAVES
        self.T1 = 0
        self.bal_start_voltage = 0
        self.bal_threshold = 0
        self.ext_bal_en = False
        self.bal_en = False

    def nr_of_slaves(self):
        count = 0
        for i in range(self.MAX_NR_OF_SLAVES):
            if self.slaves[i] is not None:
                count += 1
        return count

    def push(self, BMSSlave = None):
        for i in range(self.MAX_NR_OF_SLAVES):
            if self.slaves[i] is None:
                self.slaves[i] = BMSSlave
                return self.slaves[i]
        return None
    
    def pop(self, mac):
        for i in range(self.MAX_NR_OF_SLAVES):
            if self.slaves[i] is not None and self.slaves[i].mac == mac:
                self.slaves[i] = None
                return True
        return False
    
    def get_by_mac(self,mac):
        for i in range(self.MAX_NR_OF_SLAVES):
            if self.slaves[i] is not None and self.slaves[i].mac == mac:
                return self.slaves[i]
        return None
    
    def get_by_addr(self,addr):
        for i in range(self.MAX_NR_OF_SLAVES):
            if self.slaves[i] is not None and self.slaves[i].string_address == addr:
                return self.slaves[i]
        return None

    def is_known(self, mac):
        for i in range(self.MAX_NR_OF_SLAVES):
            if self.slaves[i] is not None and self.slaves[i].mac == mac:
                return True
        return False
    
    def sync_slaves(self, e):
        self.T1 = time.ticks_us()
        e.send(BROADCAST, pack_sync_req(self.T1))

    def check_sync_ack(self, msg, mac, e):
        T2 = msg.get("T2")
        s = self.get_by_mac(mac)
        deadline = time.ticks_add(self.T1, SYNC_DEADLINE)
        if time.ticks_diff(deadline, time.ticks_us()) > 0:
            print("ACK from", binascii.hexlify(mac, ':'), "T2=", T2)
            s.last_seen = time.ticks_us()
            T3 = time.ticks_us()
            e.send(mac, pack_sync_ref(self.T1, T2, T3))
        else:
            # MAC garbage collector will handele this
            print("Late ACK from", binascii.hexlify(mac, ':'), "ignored")

    async def sync_slaves_task(self,e):
        while True:
            self.sync_slaves(e)
            await asyncio.sleep(SLAVE_SYNC_INTERVAL)

    async def slave_gc(self):
        while True:
            now = time.ticks_us()
            for i in range(self.MAX_NR_OF_SLAVES):
                if self.slaves[i] is not None:
                    diff = time.ticks_diff(now, self.slaves[i].last_seen)
                    if diff > SLAVE_TTL * 1_000_000:
                        print("Removing inactive slave:", binascii.hexlify(self.slaves[i].mac, ':'))
                        self.slaves[i] = None
            await asyncio.sleep(SLAVE_TTL)
    
class BMSSlave(Slaves):
    def __init__(self, mac):
        self.mac = mac
        self.string_address = 0x0
        self.nr_of_cells = 0
        self.fw_version = "0.0.0.0"
        self.hw_version = "0.0.0.0"
        self.last_seen = time.ticks_us()
        self.synced = False
        self.configured = False

    def configure(self, e):
        e.send(self.mac, pack_config_msg(self.bal_start_voltage, self.bal_threshold,self.ext_bal_en,self.bal_en))

slaves = Slaves()
# ========================================
# Listen for slaves
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
            if msg_type == HELLO_MSG:
                if slaves.is_known(mac) == False:
                    #   Check if Battery string Address matches into setup
                    e.add_peer(mac)
                    s = slaves.push(BMSSlave(mac))#create new slave instance and add to list
                    #TODO: validate values within class, using setters
                    s.string_address = dict.get("str_addr")
                    s.nr_of_cells = dict.get("ncell")
                    s.fw_version = dict.get("fw_ver")
                    s.hw_version = dict.get("hw_ver")
                    print("Discovered:", binascii.hexlify(mac, ':'))
                    e.send(mac, WELCOME_MSG) # puts slave into sync state


            # Handle SYNC ACK messages
            elif msg_type == SYNC_ACK_MSG:
                if slaves.is_known(mac) == False:
                    e.send(mac, pack_reconnect())
                else:
                    slaves.check_sync_ack(dict, mac, e)

            # Handle SYNC FIN messages
            elif msg_type == SYNC_FIN_MSG:  # slave is in synced mode... waiting for config
                if slaves.is_known(mac) == False:
                    e.send(mac, pack_reconnect())
                else:
                    s = slaves.get_by_mac(mac)
                    s.last_seen = time.ticks_us()
                    s.synced = True
                    s.configure(e)

            # Handle CONFIG ACK messages
            elif msg_type == CONF_ACK_MSG:  # slave is configured and runs
                if slaves.is_known(mac) == False:
                    e.send(mac, pack_reconnect())
                else:
                    s = slaves.get_by_mac(mac)
                    s.last_seen = time.ticks_us()
                    s.configured = True   
            
            # Handle DATA messages
            elif msg_type == DATA_MSG:
                if slaves.is_known(mac) == False:
                    e.send(mac, pack_reconnect())
                else:
                    s = slaves.get_by_mac(mac)
                    s.last_seen = time.ticks_us()
                    # TODO: Add method which handles incomming data:
                    print("Data from", binascii.hexlify(mac, ':'), ":", dict)

            # Handle Unknown messages
            else:
                e.send(mac, pack_reconnect())
                print("Unknown message type from", binascii.hexlify(mac, ':'), "msg:", msg)



async def main():
    e.irq(listener)
    # Start NTP sync task
    ntp_sync_task = asyncio.create_task(ntp_task())
    slave_sync_task = asyncio.create_task(slaves.sync_slaves_task(e))
    while True:
        await asyncio.sleep(5)

# Run the async loop
asyncio.run(main())