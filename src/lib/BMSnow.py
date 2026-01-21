import espnow
import micropython
import asyncio
import network
import time
import binascii
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
        self.log.info(f"Received SEARCH_MSG from {self.log.mac_to_str(mac)}", ctx="search_handler")



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
        rsp = pack_hello_msg()
        crc = binascii.crc32(rsp)
        crc_bytes = crc.to_bytes(4, 'little')
        self.e.send(mac, rsp)
        self.log.info("Sent HELLO to master", ctx="slave connect")       

    async def start(self):
        super().start()
        asyncio.create_task(self._wlan_channel_monitor_task)
