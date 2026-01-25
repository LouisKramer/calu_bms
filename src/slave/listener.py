import network
import espnow
import time
import json
from machine import RTC
from common.common import *
from common.logger import *
import asyncio

class Slave:
    def __init__(
        self, config,
        string_address: int = 0,
        nr_cells: int = 0,
        nr_temps: int = 0,
        fw_version: str = "0.0.0.0",
        hw_version: str = "0.0.0.0",
        espnow: espnow.ESPnow = None ):

        # config
        self.config_valid = True
        self.string_address = string_address
        self.nr_cells = nr_cells
        self.nr_temps = nr_temps
        self.fw_version = fw_version
        self.hw_version = hw_version
        self.bal_start_voltage  = config.get('balancing_start_voltage', 3.4)
        self.bal_threshold      = config.get('balancing_threshold', 0.01)
        self.bal_en             = config.get('balancing_en', True)
        self.ext_bal_en         = config.get('balancing_ext_en', False)
        self.ttl                = config.get('ttl', 3600)
        self.sync_interval      = config.get('sync_interval', 10)
        # data
        self.vcell = [0]*nr_cells
        self.vstr = 0
        self.temps = [0]*nr_temps
        # commands
        self.esp_handler = ESPNowSlave(self,espnow)

    def set_config(self, msg):
        self.bal_start_voltage, self.bal_threshold, self.ext_bal_en, self.bal_en = unpack_config_msg(msg)

class ESPNowSlave():
    def __init__(
        self,
        slave: Slave = None,
        espnow: espnow.ESPNow = None
    ):
        self.slave = slave # reference to parent class
        self.master_mac = b''
        self.log = create_logger("slave", level=LogLevel.INFO)

        self.offset_us = 0
        self.last_sync_us = time.ticks_us()
        self.connected = False
        self.synced = False
        self.config_received = False
        self.sync_timeout_us = self.slave.sync_interval * 1000000
        # NTP sync timestamps
        self.T1 = self.T2 = self.T3 = self.T4 = None
        self.log.info("Start esp connection...", ctx="ESPNowSlave")
        self.e = espnow

    # -------------------------------------------------
    # Private helpers
    # -------------------------------------------------
    def _apply_offset(self):
        """Apply stored offset_us to RTC (sub-second only)."""
        dt = list(self.rtc.datetime())
        subsec = dt[7] + self.offset_us
        seconds_carry = subsec // 1_000_000
        dt[7] = subsec % 1_000_000

        secs = dt[6] + seconds_carry
        mins_carry = secs // 60
        dt[6] = secs % 60

        hrs = dt[5] + mins_carry
        dt[5] = hrs % 60
        # Higher carry (days etc.) ignored – offset is always small

        self.rtc.datetime(tuple(dt))

    def _handle_search(self, sender_mac: bytes):
        self.log.info(f"Received SEARCH from {self.log.mac_to_str(sender_mac)}", ctx="slave connect")
        if self.master_mac == b'':
            self.master_mac = sender_mac
            self.e.add_peer(sender_mac)
        self.e.send(
            sender_mac,
            pack_hello_msg(
                self.slave.string_address,
                self.slave.nr_cells,
                self.slave.nr_temps,
                self.slave.fw_version,
                self.slave.hw_version,
            ),
        )
        self.log.info("Sent HELLO to master", ctx="slave connect")

    def _handle_welcome(self, sender_mac: bytes, msg):
        if self.master_mac == sender_mac:
            ntp_time = unpack_welcome(msg)
            RTC().datetime(time.gmtime(ntp_time // 1_000_000))
            self.log.info(f"RTC set to UTC: {RTC().datetime()}", ctx="slave connect")
        else:
            self.e.del_peer(self.master_mac)
            self.master_mac = sender_mac
            self.e.add_peer(self.master_mac)
        self.connected = True
        self.log.info("Connected to master", ctx="slave connect")

    def _handle_sync_req(self, sender_mac: bytes, msg):
        if sender_mac != self.master_mac:
            self.log.warn("SYNC_REQ from unknown master", ctx="slave sync")
            return
        self.T1 = unpack_sync_req(msg)
        self.T2 = time.ticks_us()
        self.e.send(sender_mac, pack_sync_ack(self.T1, self.T2))

    def _handle_sync_ref(self, sender_mac: bytes, msg):
        if sender_mac != self.master_mac:
            self.log.warn("SYNC_REF from unknown master", ctx="slave sync")
            return

        T1_m, T2_m, T3 = unpack_sync_ref(msg)
        if self.T1 != T1_m or self.T2 != T2_m:
            self.log.warn("SYNC_REF timestamp mismatch – ignoring", ctx="slave sync")
            return

        self.T4 = time.ticks_us()
        rtt = time.ticks_diff(self.T4, self.T1) - time.ticks_diff(T3, self.T2)
        offset = (time.ticks_diff(self.T2, self.T1) + time.ticks_diff(T3, self.T4)) // 2

        self.offset_us = offset
        self._apply_offset()
        self.last_sync_us = time.ticks_us()

        self.log.info(f"NTP sync: offset={offset}µs RTT={rtt}µs", ctx="slave sync")
        self.e.send(sender_mac, pack_sync_fin(self.T1, self.T2, T3, self.T4))
        self.synced = True

    #def _handle_reconnect(self, sender_mac: bytes):
    #    if sender_mac != self.master_mac:
    #        self.log.warn("RECONNECT from unknown master", ctx="slave reconnect")
    #        return
    #    self.e.send(
    #        sender_mac,
    #        pack_hello_msg(
    #            self.string_address,
    #            self.nr_cells,
    #            self.nr_temps,
    #            self.fw_version,
    #            self.hw_version,
    #        ),
    #    )
    #    self.log.info("Master requested reconnect – sent HELLO", ctx="slave reconnect")

    def _handle_config(self, sender_mac: bytes, msg):
        if sender_mac != self.master_mac:
            self.log.warn("CONF_MSG from unknown master", ctx="slave config")
            return
        try:
            self.slave.set_config(msg)
            self.e.send(sender_mac, pack_conf_ack())
            self.log.info("Received config from master", ctx="slave config")
            self.config_received = True
        except Exception as e:
            self.log.warn(e, ctx="slave config")

    def _handle_data_request(self, sender_mac):
        if sender_mac != self.master_mac:
            self.log.warn("DATA_REQ_MSG from unknown master", ctx="slave config")
            return   
        self.e.send(sender_mac, pack_data_msg(self.slave.vcell, self.slave.data.vstr, self.slave.data.temp))
    # -------------------------------------------------
    # Public IRQ callback (process ONE message only!)
    # -------------------------------------------------
    def irq_callback(self,e):
        self.log.info("IRQ received", ctx="slave irq")
        mac, msg = self.e.irecv(0)  # non-blocking
        if mac is None or not msg:
            return
        msg_type = msg[0]

        if msg_type == SEARCH_MSG:
            self._handle_search(mac)

        elif msg_type == WELCOME_MSG:
            self._handle_welcome(mac, msg)

        elif msg_type == SYNC_REQ_MSG:
            self._handle_sync_req(mac, msg)

        elif msg_type == SYNC_REF_MSG:
            self._handle_sync_ref(mac, msg)

        #elif msg_type == RECONECT_MSG:
        #    self._handle_reconnect(mac)

        elif msg_type == CONF_MSG:
            self._handle_config(mac, msg)

        elif msg_type == DATA_REQ_MSG:
            self._handle_data_request(mac)

    # -------------------------------------------------
    # Watchdog check (call periodically)
    # -------------------------------------------------
    def check_sync(self):
        if time.ticks_diff(time.ticks_us(), self.sync_timeout_us) > self.sync_timeout_us:
            self.log.warn("No sync from master for >10s – possible clock drift!", ctx="slave watchdog")
            self.last_sync_us = time.ticks_us()  # prevent log spam
            self.synced = False
    
    async def sync_superviser_task(self):
        while True:
            self.check_sync()
            await asyncio.sleep(5)