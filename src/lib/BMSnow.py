import espnow
import micropython
import asyncio
import network
import time
import binascii
import struct
import machine
from machine import RTC
from common.logger import *
from common.credentials import *
from common.common import *
from lib.virt_slave import *


class BMSnowProtocol:
    # Message types
    SEARCH_MSG    = 10
    HELLO_MSG     = 20
    WELCOME_MSG   = 30
    DATA_MSG      = 40
    DATA_REQ_MSG  = 50
    CONF_MSG      = 60
    CONF_ACK_MSG  = 70
    SYNC_REQ_MSG  = 80
    SYNC_ACK_MSG  = 90
    SYNC_REF_MSG  = 100
    SYNC_FIN_MSG  = 110

    BROADCAST = b'\xff\xff\xff\xff\xff\xff'

    @staticmethod
    def pack_search_msg():
        return struct.pack('<B', BMSnowProtocol.SEARCH_MSG)

    @staticmethod
    def pack_hello_msg(info):
        fw_bytes = info.fw_ver.encode('utf-8')[:31] + b'\x00' * (32 - len(info.fw_ver.encode('utf-8')[:31]))
        hw_bytes = info.hw_ver.encode('utf-8')[:31] + b'\x00' * (32 - len(info.hw_ver.encode('utf-8')[:31]))
        payload = struct.pack('<BBHH32s32s',
                              BMSnowProtocol.HELLO_MSG,
                              info.addr,
                              info.ncell,
                              info.ntemp,
                              fw_bytes,
                              hw_bytes)
        #crc = binascii.crc32(payload).to_bytes(4, 'little')
        return payload# + crc

    @staticmethod
    def unpack_hello_msg(msg: bytes, info):
        payload = msg[:-4]
        #crc_calc = binascii.crc32(payload)
        #crc_rx = int.from_bytes(msg[-4:], 'little')
        values = struct.unpack('<BBHH32s32s', msg)
        info.addr   = values[1]
        info.ncell  = values[2]
        info.ntemp  = values[3]
        info.fw_ver = values[4].rstrip(b'\x00').decode('utf-8', errors='ignore')
        info.hw_ver = values[5].rstrip(b'\x00').decode('utf-8', errors='ignore')
        return info

    @staticmethod
    def pack_welcome():
        return struct.pack('<BQ', BMSnowProtocol.WELCOME_MSG, time.time())

    @staticmethod
    def unpack_welcome(msg: bytes):
        return struct.unpack('<BQ', msg)[1]

    @staticmethod
    def pack_data_req_msg():
        return struct.pack('<B', BMSnowProtocol.DATA_REQ_MSG)

    @staticmethod
    def pack_data_msg(data, info):
        header = struct.pack('<BBB', BMSnowProtocol.DATA_MSG, info.ncell, info.ntemp)
        payload = struct.pack(f'<{info.ncell}f f {info.ntemp}f',
                              *data.vcell, data.vstr, *data.temps)
        return header + payload

    @staticmethod
    def unpack_data_msg(msg: bytes, data):
        typ, nc, nt = struct.unpack_from('<BBB', msg)
        payload_fmt = f'<{nc}f f {nt}f'
        payload = struct.unpack_from(payload_fmt, msg, offset=3)
        data.vcell = list(payload[:nc])
        data.vstr  = payload[nc]
        data.temps = list(payload[nc+1:])
        return data

    @staticmethod
    def pack_config_msg(conf):
        return struct.pack('<Bff??',
                           BMSnowProtocol.CONF_MSG,
                           conf.bal_start_vol,
                           conf.bal_threshold,
                           conf.bal_en,
                           conf.bal_ext_en)

    @staticmethod
    def unpack_config_msg(msg: bytes, conf):
        values = struct.unpack('<Bff??', msg)
        conf.bal_start_vol   = values[1]
        conf.bal_threshold   = values[2]
        conf.bal_en          = values[3]
        conf.bal_ext_en      = values[4]
        return conf

    @staticmethod
    def pack_conf_ack():
        return struct.pack('<B', BMSnowProtocol.CONF_ACK_MSG)

class BMSnowComm:
    def __init__(self, role: str):
        self.role = role.lower()
        self.log = create_logger(f"BMSnow-{role}", level=LogLevel.INFO)
        self.log.info(f"Init BMSnow")
        self.e = espnow.ESPNow()
        self.e.active(True)
        self.e.add_peer(BMSnowProtocol.BROADCAST)
        self.protocol = BMSnowProtocol()

    def start(self):
        self.log.info(f"{self.role} communication layer started")
        self.e.irq(self._on_recv_irq)

    def _on_recv_irq(self):
        """Fast IRQ handler - schedule processing"""
        try:
            while True:
                mac, msg = self.e.irecv(timeout_ms=0)
                if mac is None:
                    break
                if msg:
                    micropython.schedule(self._process_message, mac, msg)
        except Exception as e:
            self.log.error(f"IRQ receive error: {e}")

    def _process_message(self, mac, msg):
        """Scheduled from IRQ - can take more time"""
        if not msg or len(msg) == 0:
            return

        msg_type = msg[0]
        # Here you would normally set self.state.com_active = True
        # but state belongs to the concrete role instance

        handler_map = self.get_message_handlers()
        handler = handler_map.get(msg_type)

        if handler:
            try:
                handler(mac, msg)
            except Exception as e:
                self.log.error(f"Handler failed for type {msg_type}: {e}")
        else:
            self.log.info(f"Ignored unknown message type {msg_type}")

    def get_message_handlers(self):
        """To be overridden by subclasses"""
        return {}

    def send(self, mac, data):
        try:
            self.e.send(mac, data)
        except Exception as e:
            self.log.warn(f"Send failed to {self.log.mac_to_str(mac)}: {e}")

class BMSnowMaster(BMSnowComm):
    def __init__(self, slaves: Slaves):
        super().__init__("master")
        self.slaves = slaves

    def get_message_handlers(self):
        return {
            BMSnowProtocol.HELLO_MSG:    self._handle_hello,
            BMSnowProtocol.DATA_MSG:     self._handle_data,
            BMSnowProtocol.CONF_ACK_MSG: self._handle_conf_ack,
            # Add others as needed
        }

    async def start(self):
        self.log.info("Start BMSnowMaster")
        super().start()
        asyncio.create_task(self._discovery_task())

    async def _discovery_task(self):
        while True:
            try:
                self.discover()
                self.log.info("Broadcasting SEARCH message")
            except Exception as e:
                self.log.warn(f"Discovery broadcast failed: {e}")
            await asyncio.sleep(5)

    def discover(self):
        self.send(BMSnowProtocol.BROADCAST, BMSnowProtocol.pack_search_msg())

    async def request_data_task(self):
        while True:
            try:
                self.request_all_data()
            except Exception as e:
                self.log.warn(f"Request data failed: {e}")
            await asyncio.sleep(2)

    def request_data(self, battery):
        if battery.info.mac:
            self.send(battery.info.mac, BMSnowProtocol.pack_data_req_msg())
            self.log.info(f"Requested data from slave {battery.info.addr}")

    def request_all_data(self):
        for s in self.slaves:
            self.request_data(s.battery)

    def configure(self, battery):
        if battery.info.mac:
            self.send(battery.info.mac, BMSnowProtocol.pack_config_msg(battery.conf))
            self.log.info(f"Sent configuration to {battery.info.addr}")

    def configure_all(self):
        for s in self.slaves:
            self.configure(s.battery)

    # Handlers
    def _handle_hello(self, mac, msg):
        info = info_data()
        self.protocol.unpack_hello_msg(msg, info)
        info.mac = mac

        s = self.slaves.get_by_mac(mac)
        if s is None:
            self.e.add_peer(mac)
            self.slaves.push(info)
            self.log.info(f"New slave discovered: {self.log.mac_to_str(mac)}")
        else:
            s.battery.info.set(info)

        self.send(mac, self.protocol.pack_welcome())

    def _handle_data(self, mac, msg):
        s = self.slaves.get_by_mac(mac)
        if s:
            self.protocol.unpack_data_msg(msg, s.battery.meas)
            self.log.info(f"Received data from {self.log.mac_to_str(mac)}")
        else:
            self.log.warn(f"Data from unknown slave: {self.log.mac_to_str(mac)}")

    def _handle_conf_ack(self, mac, msg):
        s = self.slaves.get_by_mac(mac)
        if s:
            self.log.info(f"Config ACK received from {self.log.mac_to_str(mac)}")
        else:
            self.log.warn(f"Config ACK from unknown: {self.log.mac_to_str(mac)}")

class BMSnowSlave(BMSnowComm):
    WLAN_CHANNELS = range(1, 14)

    def __init__(self, battery):
        super().__init__("slave")
        self.battery = battery
        self.info = battery.info
        self.data = battery.meas
        self.conf = battery.conf
        self.state = battery.state

    def get_message_handlers(self):
        return {
            BMSnowProtocol.SEARCH_MSG:   self._handle_search,
            BMSnowProtocol.WELCOME_MSG:  self._handle_welcome,
            BMSnowProtocol.DATA_REQ_MSG: self._handle_data_request,
            BMSnowProtocol.CONF_MSG:     self._handle_config,
        }

    async def start(self):
        super().start()
        asyncio.create_task(self._channel_monitor_task())

    async def _set_channel(self, ch):
        try:
            sta = network.WLAN(network.STA_IF)
            sta.active(True)
            sta.config(channel=ch)
            await asyncio.sleep_ms(50)
        except Exception as e:
            self.log.warn(f"Failed to set channel {ch}: {e}")

    async def _channel_monitor_task(self):
        while True:
            if not self.state.channel_found:
                self.log.info("Channel not found - starting scan")
                for ch in self.WLAN_CHANNELS:
                    await self._set_channel(ch)
                    await asyncio.sleep(15)
            else:
                if self.state.ttl <= 0:
                    self.log.warning("Communication timeout - restarting scan")
                    self.state.channel_found = False
                    self.state.ttl = self.conf.ttl
                elif self.state.com_active:
                    self.state.ttl = self.conf.ttl
                    self.state.com_active = False
                else:
                    self.state.ttl -= 1

            await asyncio.sleep(30)

    def _handle_search(self, mac, msg):
        self.state.channel_found = True

        if self.info.master_mac == b'':
            self.info.master_mac = mac
            self.e.add_peer(mac)

        response = self.protocol.pack_hello_msg(self.info)
        self.send(mac, response)
        self.log.info(f"Responded to SEARCH from {self.log.mac_to_str(mac)}")

    def _handle_welcome(self, mac, msg):
        if mac == self.info.master_mac:
            try:
                unix_seconds = self.protocol.unpack_welcome(msg)  # now real Unix timestamp
                rtc = machine.RTC()
                # Convert Unix seconds → RTC tuple (UTC)
                tm = time.gmtime(unix_seconds)
                # RTC tuple: (year, month, day, weekday, hour, minute, second, subseconds)
                # MicroPython RTC weekday: 0=Mon ... 6=Sun (gmtime gives 0=Mon ... 6=Sun → compatible)
                rtc_tuple = (tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0)
                rtc.datetime(rtc_tuple)

                self.log.info(f"RTC set to UTC from master: {rtc.datetime()}")
                self.log.info("Connected & time synchronized")
            except Exception as e:
                self.log.error(f"Failed to set RTC from WELCOME: {e}")

    def _handle_data_request(self, mac, msg):
        if mac == self.info.master_mac:
            data_msg = self.protocol.pack_data_msg(self.data, self.info)
            self.send(mac, data_msg)
            self.log.info("Sent measurement data")
        else:
            self.log.warn("Data request from unknown master")

    def _handle_config(self, mac, msg):
        if mac == self.info.master_mac:
            conf = conf_data()
            self.protocol.unpack_config_msg(msg, conf)
            self.conf.set(conf)
            self.send(mac, self.protocol.pack_conf_ack())
            self.log.info("Configuration updated")
        else:
            self.log.warn("Config from unknown master")
