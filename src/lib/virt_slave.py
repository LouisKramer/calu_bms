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

    def __init__(self, config):
        log_slave.info("Initializing slave handler...", ctx="slave_handler")
        self.cfg = config
        self.bal_start_voltage = config.get('balancing_start_voltage', 3.4)
        self.bal_threshold = config.get('balancing_threshold', 0.01)
        self.bal_en = config.get('balancing_en', True)
        self.ext_bal_en = config.get('balancing_ext_en', False)
        self.ttl = config.get('ttl', 3600)
        self.sync_interval = config.get('sync_interval', 10)
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
    #  Helper to enforce the hard limit
    # ------------------------------------------------------------------
    def _ensure_capacity(self):
        """Raise if we would exceed the hard limit."""
        if len(self._slaves) >= self.MAX_NR_OF_SLAVES:
            log_slave.warn(f"Cannot add more than {self.MAX_NR_OF_SLAVES} slaves", ctx="slave handler")

    # ------------------------------------------------------------------
    #  Core CRUD operations 
    # ------------------------------------------------------------------
    def push(self, virt_slave=None):
        """Add a new slave if there is room; return the stored instance."""
        log_slave.info(f"Add slave {log_slave.mac_to_str(virt_slave.mac)} to list", ctx="slave handler")
        self._ensure_capacity()
        self._slaves.append(virt_slave)
        return virt_slave

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
            if s is not None and s.mac == mac:
                return s
        return None

    def get_by_addr(self, addr):
        for s in self._slaves:
            if s is not None and s.string_address == addr:
                return s
        return None

    def is_known(self, mac) -> bool:
        return any(s is not None and s.mac == mac for s in self._slaves)

    # ------------------------------------------------------------------
    #  Data aggregation 
    # ------------------------------------------------------------------
    def get_nr_of_total_cells(self) -> int:
        total = 0
        for slave in self._slaves:
            if slave and hasattr(slave, "nr_of_cells") and slave.vstr:
                total += slave.nr_of_cells
        return total

    def _sorted_by_address(self, attr):
        """Helper used by the three “get_all_*” methods."""
        items = []
        for slave in self._slaves:
            if slave and hasattr(slave, attr) and getattr(slave, attr):
                items.append((slave.string_address, getattr(slave, attr)))
        items.sort(key=lambda x: x[0])
        return [val for _, val in items]

    def get_all_cell_voltages(self):
        return self._sorted_by_address("vcell")

    def get_all_str_voltages(self):
        return self._sorted_by_address("vstr")

    def get_all_temperatures(self):
        return self._sorted_by_address("temp")

    # ------------------------------------------------------------------
    #  discover
    # ------------------------------------------------------------------
    def discover_slaves(self, e):
        try:
            e.send(BROADCAST, pack_search_msg())
            log_slave.info("Discovering slaves:", ctx="slave discover")
        except Exception as e:
            log_slave.warn(e, ctx="slave discover")
    # ------------------------------------------------------------------
    #  discover
    # ------------------------------------------------------------------
    def request_data_from_slaves(self, e):
        try:
            e.send(None, pack_data_req_msg())
            log_slave.info("Request data from slaves:", ctx="slave data request")
        except Exception as e:
            log_slave.warn(e, ctx="slave discover")
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

            # ---------- HELLO ----------
            if msg_type == HELLO_MSG:
                if not self.is_known(mac):
                    e.add_peer(mac)
                    s = self.push(virt_slave(mac))
                    s.set_info(msg)
                    log_slave.info(f"Discovered: {log_slave.mac_to_str(mac)}", ctx="slave handler")
                e.send(mac, pack_welcome(time.ticks_us()))

            # ---------- SYNC ACK ----------
            elif msg_type == SYNC_ACK_MSG:
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
                    s.configure(e)

            # ---------- CONFIG ACK ----------
            elif msg_type == CONF_ACK_MSG:
                if not self.is_known(mac):
                    e.send(mac, pack_reconnect())
                else:
                    s = self.get_by_mac(mac)
                    s.last_seen = time.ticks_us()
                    s.configured = True

            # ---------- DATA ----------
            elif msg_type == DATA_MSG:
                if not self.is_known(mac):
                    e.send(mac, pack_reconnect())
                else:
                    s = self.get_by_mac(mac)
                    s.last_seen = time.ticks_us()
                    s.data(msg)
                    log_slave.info(f"Data form: {log_slave.mac_to_str(mac)} : {dict_}", ctx="slave handler")

            # ---------- UNKNOWN ----------
            else:
                #e.send(mac, pack_reconnect())
                log_slave.warn(f"Unknown message type from: {log_slave.mac_to_str(mac)}", ctx="slave handler")
    
class virt_slave(Slaves):
    def __init__(self, mac):
        self.mac = mac
        self.string_address = 0x0  # 0-15
        self.nr_of_cells = 0  # 0-32
        self.nr_of_temps = 0       # 0-4
        self.fw_version = "0.0.0.0"
        self.hw_version = "0.0.0.0"
        self.last_seen = time.ticks_us()
        self.synced = False
        self.configured = False
        self.vcell = []
        self.temp = []
        self.vstr = 0.0

    def configure(self, e):
        e.send(self.mac, pack_config_msg(self.bal_start_voltage, self.bal_threshold, self.ext_bal_en, self.bal_en))

    def data(self,msg):
        vcell, vstr, temp = unpack_data_msg(msg)
        if vcell is not None:
            if isinstance(vcell, list) and len(vcell) == self.nr_of_cells:
                if all(isinstance(v, (int, float)) and 0.0 <= v <= 5.0 for v in vcell):
                    self.vcell = [float(v) for v in vcell]
        if temp is not None:
            if isinstance(temp, list) and len(temp) > 0 and len(temp) <= 4:
                if all(isinstance(t, (int, float)) and -50.0 <= t <= 150.0 for t in temp):
                    self.temp = [float(t) for t in temp]
        if vstr is not None:
            if isinstance(vstr, (int, float)) and (0.0 <= vstr <= 160.0):
                self.vstr = vstr

    def set_info(self, msg):
        s_addr, ncell, ntemp, fw_ver, hw_ver= unpack_hello_msg(msg)
        if  isinstance(s_addr, int) or (0 <= s_addr <= 15):
            self.string_address = s_addr
       
        if isinstance(ncell, int) or (0 <= ncell <= 16):
            self.nr_of_cells = ncell

        if isinstance(ncell, int) or (0 <= ntemp <= 16):
            self.nr_of_temps = ntemp

        if isinstance(fw_ver, str):
            parts = fw_ver.split('.')
            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                self.fw_version = fw_ver

        if isinstance(hw_ver, str):
            parts = hw_ver.split('.')
            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                self.hw_version = hw_ver
    
    def get_cell_voltage(self, cell):
        if 0 <= cell < self.nr_of_cells:
            return self.vcell[cell]
        else:
            return None
        
    def get_all_cell_voltages(self):
        return self.vcell
    
    def get_string_voltage(self):
        return self.vstr
    
    def get_all_temperatures(self):
        return self.temp

