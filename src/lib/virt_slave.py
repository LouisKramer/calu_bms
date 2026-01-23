import time, binascii, os, json
from common.common import *
from common.logger import *
import asyncio

log_slave=create_logger("slave_handler", level=LogLevel.INFO)

# ----------------------------------------------------------------------
#  Slaves – dynamic container with a hard upper limit (MAX_NR_OF_SLAVES)
# ----------------------------------------------------------------------
class Slaves:
    MAX_NR_OF_SLAVES = 16    
    def __init__(self):
        log_slave.info("Initializing slave handler...", ctx="slave_handler")

        self.T1 = 0
        # start with an *empty* list – we grow only when push() is called
        self._slaves: list["virt_slave | None"] = []

    # ------------------------------------------------------------------
    #  Basic bookkeeping
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        """Number of active (non-None) slaves."""
        return sum(1 for s in self._slaves if s is not None)

    def __iter__(self):
        """Iterate over active slaves only."""
        return (s for s in self._slaves if s is not None)

    def nr_of_slaves(self) -> int:
        return len(self)

    # ------------------------------------------------------------------
    #  Core CRUD operations 
    # ------------------------------------------------------------------
    def push(self, info: info_data):
        """Add a new slave if there is room"""
        if len(self._slaves) >= self.MAX_NR_OF_SLAVES:
            log_slave.warn(f"Cannot add more than {self.MAX_NR_OF_SLAVES} slaves", ctx="slave handler")
        else:
            log_slave.info(f"Add slave {log_slave.mac_to_str(info.mac)} to list", ctx="slave handler")
            new = virt_slave(info)
            self._slaves.append(new)

    def pop(self, mac) -> bool:
        """Remove slave identified by MAC address."""
        for i, s in enumerate(self._slaves):
            if s is not None and s.mac == mac:
                self._slaves[i] = None          # keep a hole – list stays compact
                return True
        log_slave.warn(f"Unable to remove slave {log_slave.mac_to_str(mac)} from list", ctx="slave handler")
        return False

    def get_by_mac(self, mac):
        for s in self._slaves:
            if s is not None and s.battery.info.mac == mac:
                return s
        return None

    def get_by_addr(self, addr):
        for s in self._slaves:
            if s is not None and s.battery.info.addr == addr:
                return s
        return None

    def is_known(self, mac) -> bool:
        return any(s is not None and s.battery.info.mac == mac for s in self._slaves)

    # ------------------------------------------------------------------
    #  Sync / GC helpers 
    # ------------------------------------------------------------------
    def sync_slaves(self, e):
        self.T1 = time.ticks_us()
        e.send(None, pack_sync_req(self.T1)) # send sync to all peers

    def check_sync_ack(self, msg, mac, e):
        T1,T2 = unpack_sync_ack(msg)
        s = self.get_by_mac(mac)
        deadline = time.ticks_add(self.T1, SYNC_DEADLINE)
        if time.ticks_diff(deadline, time.ticks_us()) > 0:
            log_slave.info(f"ACK from {log_slave.mac_to_str(mac)} T2={T2}", ctx="slave sync")
            s.last_seen = time.ticks_us()
            T3 = time.ticks_us()
            e.send(mac, pack_sync_ref(self.T1, T2, T3))
        else:
            log_slave.warn("Late ACK from", log_slave.mac_to_str(mac), "ignored", ctx="slave handler")

    async def sync_slaves_task(self, e):
        while True:
            try: 
                self.sync_slaves(e)
                log_slave.info("Syncing slaves:", ctx="slave sync")
            except Exception as e:
                log_slave.warn(e, ctx="slave sync")
            await asyncio.sleep(self.sync_interval)

    async def slave_gc(self):
        while True:
            log_slave.info(f"Run slave GC", ctx="slave handler")
            now = time.ticks_us()
            for slave in self._slaves:
                if slave and time.ticks_diff(now, slave.last_seen) > self.ttl * 1_000_000:
                    log_slave.info("Removing inactive slave:", log_slave.mac_to_str(slave.mac), ctx="slave sync")
                    # replace with None – keeps the list length stable
                    self._slaves[self._slaves.index(slave)] = None
            await asyncio.sleep(self.ttl)

    # ------------------------------------------------------------------
    #  Message listener 
    # ------------------------------------------------------------------
    def slave_listener(self, e):
        while True:
            mac, msg = e.irecv(0)
            if mac is None or not msg:
                return
            log_slave.info(f"Received message from: {log_slave.mac_to_str(mac)}", ctx="slave handler")    
            msg_type = msg[0]

            # ---------- SYNC ACK ----------
            if msg_type == SYNC_ACK_MSG:
                if not self.is_known(mac):
                    e.send(mac, pack_reconnect())
                else:
                    self.check_sync_ack(msg, mac, e)

            # ---------- SYNC FIN ----------
            elif msg_type == SYNC_FIN_MSG:
                if not self.is_known(mac):
                    e.send(mac, pack_reconnect())
                else:
                    s = self.get_by_mac(mac)
                    s.last_seen = time.ticks_us()
                    s.synced = True

            # ---------- UNKNOWN ----------
            else:
                #e.send(mac, pack_reconnect())
                log_slave.warn(f"Unknown message type from: {log_slave.mac_to_str(mac)}", ctx="slave handler")
    
class virt_slave(Slaves):
    def __init__(self, info: info_data):
        self.battery = battery()
        self.battery.info.set (info_data)
        self.battery.create_measurements()
    
