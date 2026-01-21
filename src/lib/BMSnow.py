import espnow
import micropython
import asyncio
import network
import time
import binascii
import struct
from common.logger import *
from common.credentials import *

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
            if msg_type == BMSnow.DATA_MSG:
                micropython.schedule(self._handle_data_ms, mac, msg)
            if msg_type == BMSnow.DATA_REQ_MSG:
                micropython.schedule(self._handle_data_req_msg, mac, msg)
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

    def __pack_hello_msg(self, addr, ncell, ntemp, fw_ver, hw_ver):
        # Prepare fixed 32-byte null-padded versions (truncate at 31 chars to leave room for null if desired)
        fw_bytes = fw_ver.encode('utf-8')[:31]
        fw_bytes += b'\x00' * (32 - len(fw_bytes))          # pad to exactly 32 bytes

        hw_bytes = hw_ver.encode('utf-8')[:31]
        hw_bytes += b'\x00' * (32 - len(hw_bytes))

        payload = struct.pack('<BBHH32s32s', self.HELLO_MSG, addr, ncell, ntemp, fw_bytes, hw_bytes)
        crc = binascii.crc32(payload).to_bytes(4, 'little')
        return payload + crc
    
    def __unpack_hello_msg(self, msg):
        payload = msg[:-4]
        crc_calc =  binascii.crc32(payload)
        crc_rx = int.from_bytes(msg[-4:], 'little')
        if crc_calc != crc_rx:
            self.log.error(f"CRC Error!", ctx="slave discovery")
            return

        value = struct.unpack('<BBHH32s32s', payload)
        addr = value[1]
        ncell = value[2]
        ntemp = value[3]
        fw_ver = value[4].rstrip(b'\x00').decode('utf-8')
        hw_ver = value[5].rstrip(b'\x00').decode('utf-8')

        return addr, ncell, ntemp, fw_ver, hw_ver

class BMSnow_master(BMSnow):
    def __init__(self):
        super().__init__(self)
        pass
    def discover(self):
        pass
    def data(self):
        pass
    def sync(self):
        pass

    def _handle_hello_msg(self, mac, msg):
        self.log.info(f"Received HELLO_MSG from {self.log.mac_to_str(mac)}", ctx="listener")
        if not self.is_known(mac):
            e.add_peer(mac)
            s = self.push(virt_slave(mac))
            s.set_info(msg)
            self.log.info(f"Discovered: {log_slave.mac_to_str(mac)}", ctx="slave handler")
        self.e.send(mac, pack_welcome(time.ticks_us()))



class BMSnow_slave(BMSnow):
    WLAN_CHANNELS = range(1, 14)
    def __init__(self):
        super().__init__(self)
        self.master_mac = b''

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
        rsp = self.__pack_hello_msg()
        self.e.send(mac, rsp)
        self.log.info("Sent HELLO to master", ctx="slave connect")       

    async def start(self):
        super().start()
        asyncio.create_task(self._wlan_channel_monitor_task)
