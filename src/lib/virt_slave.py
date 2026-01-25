import time, binascii, os, json
from common.common import *
from common.logger import *
import asyncio

log_slave=Logger()

# ----------------------------------------------------------------------
#  Slaves – dynamic container with a hard upper limit (MAX_NR_OF_SLAVES)
# ----------------------------------------------------------------------
class Slaves:
    MAX_NR_OF_SLAVES = 16    
    def __init__(self):
        log_slave.info("Initializing slave handler...")

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
        return len(self._slaves)

    # ------------------------------------------------------------------
    #  Core CRUD operations 
    # ------------------------------------------------------------------
    def push(self, info: info_data):
        """Add a new slave if there is room"""
        if len(self._slaves) >= self.MAX_NR_OF_SLAVES:
            log_slave.warn(f"Cannot add more than {self.MAX_NR_OF_SLAVES} slaves")
            return None
        else:
            log_slave.info(f"Add slave {log_slave.mac_to_str(info.mac)} to list")
            new = virt_slave(info)
            for i, s in enumerate(self._slaves):
                if s is None:
                    self._slaves[i] = new
                    return new
            self._slaves.append(new)
            return new

    def pop(self, info: info_data) -> bool:
        """Remove slave identified by MAC address."""
        for i, s in enumerate(self._slaves):
            if s is not None and s.battery.info.mac == info.mac:
                log_slave.info(f"Remove slave {log_slave.mac_to_str(info.mac)} from list")
                del self._slaves[i]        # keep a hole – list stays compact
                return True
        log_slave.warn(f"Unable to remove slave {log_slave.mac_to_str(info.mac)} from list")
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
            log_slave.info(f"ACK from {log_slave.mac_to_str(mac)} T2={T2}")
            s.last_seen = time.ticks_us()
            T3 = time.ticks_us()
            e.send(mac, pack_sync_ref(self.T1, T2, T3))
        else:
            log_slave.warn("Late ACK from", log_slave.mac_to_str(mac), "ignored")

    async def sync_slaves_task(self, e):
        while True:
            try: 
                self.sync_slaves(e)
                log_slave.info("Syncing slaves:")
            except Exception as e:
                log_slave.warn(e)
            await asyncio.sleep(self.sync_interval)

    # ------------------------------------------------------------------
    #  Message listener 
    # ------------------------------------------------------------------
    def slave_listener(self, e):
        while True:
            mac, msg = e.irecv(0)
            if mac is None or not msg:
                return
            log_slave.info(f"Received message from: {log_slave.mac_to_str(mac)}")    
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
                log_slave.warn(f"Unknown message type from: {log_slave.mac_to_str(mac)}")
    
class virt_slave(Slaves):
    def __init__(self, info: info_data):
        self.battery = battery()
        self.battery.info.set(info)
        self.battery.create_measurements()
    
