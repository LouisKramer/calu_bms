import espnow
import micropython
import asyncio
import network
import time
import binascii
import struct
from machine import RTC
from common.logger import *
from common.credentials import *
from common.common import info_data, meas_data
from lib.virt_slave import *


class BMSnow:
    SEARCH_MSG   = 10
    HELLO_MSG    = 20
    WELCOME_MSG  = 30
    DATA_MSG     = 40
    DATA_REQ_MSG = 50
    CONF_MSG     = 60
    CONF_ACK_MSG = 70
    SYNC_REQ_MSG = 80 # Request from master to slave
    SYNC_ACK_MSG = 90  # Ack from slave to master
    SYNC_REF_MSG = 100 # Reference from master to slave
    SYNC_FIN_MSG = 110 # Final ack from slave to master

    STATUS_WLAN_CHANNEL_SCAN = 10
    STATUS_DISCOVER_MASTER = 20
    STATUS_DISCOVER_SLAVES = 30
    STATUS_CONNECTED_TO_MASTER = 40

    BROADCAST = b'\xff\xff\xff\xff\xff\xff'

    def __init__(self):
        self.log = create_logger("BMSnow", level=LogLevel.INFO)
        self.e = espnow.ESPNow()
        self.e.active(True)
    
    async def start(self):
        self.e.irq(self._listener)

    def _listener(self):
        while True:
            mac, msg = self.e.irecv(0)  # non-blocking
            if mac is None or not msg:
                return
            msg_type = msg[0]
            if msg_type == BMSnow.SEARCH_MSG:
                micropython.schedule(self._handle_search_msg,mac,msg)
            if msg_type == BMSnow.HELLO_MSG:
                micropython.schedule(self._handle_hello_msg, mac, msg)
            if msg_type == BMSnow.WELCOME_MSG:
                micropython.schedule(self._handle_welcome_msg, mac, msg)
            if msg_type == BMSnow.DATA_REQ_MSG:
                micropython.schedule(self._handle_data_req_msg, mac, msg)
            if msg_type == BMSnow.DATA_MSG:
                micropython.schedule(self._handle_data_msg, mac, msg)
            if msg_type == BMSnow.CONF_MSG:
                micropython.schedule(self._handle_conf_msg, mac, msg)
            if msg_type == BMSnow.CONF_ACK_MSG:
                micropython.schedule(self._handle_conf_ack_msg, mac, msg)
            if msg_type == BMSnow.SYNC_REQ_MSG:
                micropython.schedule(self._handle_sync_req_msg, mac, msg)
            if msg_type == BMSnow.SYNC_ACK_MSG:
               micropython.schedule( self._handle_sync_ack_msg, mac, msg)
            else:
                pass
            
    def _handle_search_msg(self, mac, msg):
        self.log.info(f"Received SEARCH_MSG from {self.log.mac_to_str(mac)}", ctx="listener")
    
    def _handle_hello_msg(self, mac, msg):
        self.log.info(f"Received HELLO_MSG from {self.log.mac_to_str(mac)}", ctx="listener")

    def _handle_welcome_msg(self, mac, msg):
        self.log.info(f"Received WELCOME MSG from {self.log.mac_to_str(mac)}", ctx="listener")

    def _handle_data_req_msg(self, mac, msg):
        self.log.info(f"Received DATA REQUEST MSG from {self.log.mac_to_str(mac)}", ctx="listener")

    @staticmethod
    def pack_search_msg():
        return struct.pack('<B', BMSnow.SEARCH_MSG)

    @staticmethod
    def pack_hello_msg(info: info_data):
        # Prepare fixed 32-byte null-padded versions (truncate at 31 chars to leave room for null if desired)
        fw_bytes = info.fw_ver.encode('utf-8')[:31]
        fw_bytes += b'\x00' * (32 - len(fw_bytes))          # pad to exactly 32 bytes

        hw_bytes = info.hw_ver.encode('utf-8')[:31]
        hw_bytes += b'\x00' * (32 - len(hw_bytes))
        payload = struct.pack('<BBHH32s32s', BMSnow.HELLO_MSG, info.addr, info.ncell, info.ntemp, fw_bytes, hw_bytes)
        crc = binascii.crc32(payload).to_bytes(4, 'little')
        return payload + crc
    
    @staticmethod
    def unpack_hello_msg(msg):
        info = info_data()
        payload = msg[:-4]
        crc_calc =  binascii.crc32(payload)
        crc_rx = int.from_bytes(msg[-4:], 'little')
        if crc_calc == crc_rx:
            value = struct.unpack('<BBHH32s32s', payload)
            info.addr = value[1]
            info.ncell = value[2]
            info.ntemp = value[3]
            info.fw_ver = value[4].rstrip(b'\x00').decode('utf-8')
            info.hw_ver = value[5].rstrip(b'\x00').decode('utf-8')
        return info
    
    @staticmethod
    def pack_welcome(now):
        return struct.pack('<BQ', BMSnow.WELCOME_MSG,now)

    @staticmethod
    def unpack_welcome(msg):
        time = struct.unpack('<BQ', msg)
        return time[1]

    @staticmethod
    def pack_data_req_msg():
        return struct.pack('<B', BMSnow.DATA_REQ_MSG)
    
    @staticmethod
    def unpack_data_req_msg():
        return 

class BMSnow_master(BMSnow):
    def __init__(self, slaves: Slaves):
        super().__init__()
        self.slaves = slaves

    def discover(self):
        try:
            self.e.send(self.BROADCAST, self.pack_search_msg())
            self.log.info("Discovering slaves:", ctx="slave discover")
        except Exception as e:
            self.log.warn(e, ctx="slave discover")

    def get_data(self, mac):
        try:
            self.e.send(mac, self.pack_data_req_msg())
            self.log.info("Request data from slaves:", ctx="slave data request")
        except Exception as e:
            self.log.warn(e, ctx="slave discover")

    def sync(self):
        pass

    def _handle_hello_msg(self, mac, msg):
        self.log.info(f"Received HELLO_MSG from {self.log.mac_to_str(mac)}", ctx="listener")
        if not self.slaves.is_known(mac):
            self.e.add_peer(mac)
            info = self.unpack_hello_msg(msg)
            self.slaves.push(mac, info)
            self.log.info(f"Discovered: {self.log.mac_to_str(mac)}", ctx="slave handler")
        self.e.send(mac, self.pack_welcome(time.ticks_us()))


class BMSnow_slave(BMSnow):
    WLAN_CHANNELS = range(1, 14)
    def __init__(self, info: info_data, data: meas_data):
        super().__init__()
        self.master_mac = b''
        self.info = info
        self.data = data
    async def _set_esp_channel(self, ch):
        try:
            network.WLAN(network.STA_IF).config(channel=ch)
            await asyncio.sleep(0.05)  # minimal settle time 30ms
        except Exception as e:
            self.log.warn(f"Channel set failed: {e}", ctx="BMSnow_slave")

    async def _wlan_channel_monitor_task(self):
        while self.status == self.STATUS_WLAN_CHANNEL_SCAN:
            for ch in self.WLAN_CHANNELS:
                self._set_esp_channel(ch)
                await asyncio.sleep(15)
            await asyncio.sleep(30)

    def _handle_search_msg(self, mac, msg):
        self.log.info(f"Received SEARCH from {self.log.mac_to_str(mac)}", ctx="slave_search_handler")
        self.status = self.STATUS_DISCOVER_MASTER
        if self.master_mac == b'':
            self.master_mac = mac
            self.e.add_peer(mac)
        rsp = self.pack_hello_msg(self.info)
        self.e.send(mac, rsp)
        self.log.info("Sent HELLO to master", ctx="slave connect")       

    def _handle_welcome_msg(self, mac, msg):
        self.log.info(f"Received WELCOME MSG from {self.log.mac_to_str(mac)}", ctx="listener")
        if self.master_mac == mac:
            ntp_time = self.unpack_welcome(msg)
            RTC().datetime(time.gmtime(ntp_time // 1_000_000))
            self.log.info(f"RTC set to UTC: {RTC().datetime()}", ctx="slave connect")
        else:
            self.e.del_peer(self.master_mac)
            self.master_mac = mac
            self.e.add_peer(self.master_mac)
        self.connected = True
        self.log.info("Connected to master", ctx="slave connect")

    def _handle_data_req_msg(self, mac, msg):
        self.log.info(f"Received DATA REQUEST MSG from {self.log.mac_to_str(mac)}", ctx="listener")
        if mac != self.master_mac:
            self.log.warn("DATA_REQ_MSG from unknown master", ctx="slave config")
        else: 
            self.e.send(mac, pack_data_msg(self.data))

    async def start(self):
        super().start()
        asyncio.create_task(self._wlan_channel_monitor_task)



    