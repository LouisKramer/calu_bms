import time, binascii
from common.common import *
import asyncio

class Slaves:
    MAX_NR_OF_SLAVES = 16

    def __init__(self, interval, ttl):
        # init max number of slaves
        self.slaves = [None]*self.MAX_NR_OF_SLAVES
        self.T1 = 0
        self.bal_start_voltage = 0
        self.bal_threshold = 0
        self.ext_bal_en = False
        self.bal_en = False
        self.interval = interval
        self.ttl = ttl
    def nr_of_slaves(self):
        count = 0
        for i in range(self.MAX_NR_OF_SLAVES):
            if self.slaves[i] is not None:
                count += 1
        return count
    
    def get_nr_of_total_cells(self):
        nr_of_total_cells=0
        for slave in self.slaves:
            if slave is not None and hasattr(slave, 'nr_of_cells') and slave.vstr:
                nr_of_total_cells = nr_of_total_cells + slave.nr_of_cells
        return nr_of_total_cells
    
    def get_all_cell_voltages(self):
        # Create a list of tuples with (string_address, vcell) for non-None slaves
        all_voltages = []
        for slave in self.slaves:
            if slave is not None and hasattr(slave, 'vcell') and slave.vcell:
                all_voltages.append((slave.string_address, slave.vcell))
        
        # Sort by string_address
        all_voltages.sort(key=lambda x: x[0])
        
        # Return just the voltages in order
        return [voltage for _, voltage in all_voltages]
    
    def get_all_str_voltages(self):
        # Create a list of tuples with (string_address, vstr) for non-None slaves
        all_voltages = []
        for slave in self.slaves:
            if slave is not None and hasattr(slave, 'vstr') and slave.vstr:
                all_voltages.append((slave.string_address, slave.vstr))
        
        # Sort by string_address
        all_voltages.sort(key=lambda x: x[0])
        
        # Return just the voltages in order
        return [voltage for _, voltage in all_voltages]

    def get_all_str_temperatures(self):
        # Create a list of tuples with (string_address, temp) for non-None slaves
        all_temps = []
        for slave in self.slaves:
            if slave is not None and hasattr(slave, 'temp') and slave.temp:
                all_temps.append((slave.string_address, slave.temp))
        
        # Sort by string_address
        all_temps.sort(key=lambda x: x[0])
        
        # Return just the temperatures in order
        return [temp for _, temp in all_temps]

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
            await asyncio.sleep(self.interval)

    async def slave_gc(self):
        #TODO: this should trigger a critical error!!!!!
        while True:
            now = time.ticks_us()
            for i in range(self.MAX_NR_OF_SLAVES):
                if self.slaves[i] is not None:
                    diff = time.ticks_diff(now, self.slaves[i].last_seen)
                    if diff > self.ttl * 1_000_000:
                        print("Removing inactive slave:", binascii.hexlify(self.slaves[i].mac, ':'))
                        self.slaves[i] = None
            await asyncio.sleep(self.ttl) #TODO: adjust time

    def slave_listener(self, e):
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
                    if self.is_known(mac) == False:
                        #   Check if Battery string Address matches into setup
                        e.add_peer(mac)
                        s = self.push(BMSSlave(mac))#create new slave instance and add to list
                        s.set_info(dict)
                        print("Discovered:", binascii.hexlify(mac, ':'))
                        e.send(mac, WELCOME_MSG) # puts slave into sync state

                # Handle SYNC ACK messages
                elif msg_type == SYNC_ACK_MSG:
                    if self.is_known(mac) == False:
                        e.send(mac, pack_reconnect())
                    else:
                        self.check_sync_ack(dict, mac, e)

                # Handle SYNC FIN messages
                elif msg_type == SYNC_FIN_MSG:  # slave is in synced mode... waiting for config
                    if self.is_known(mac) == False:
                        e.send(mac, pack_reconnect())
                    else:
                        s = self.get_by_mac(mac)
                        s.last_seen = time.ticks_us()
                        s.synced = True
                        s.configure(e)

                # Handle CONFIG ACK messages
                elif msg_type == CONF_ACK_MSG:  # slave is configured and runs
                    if self.is_known(mac) == False:
                        e.send(mac, pack_reconnect())
                    else:
                        s = self.get_by_mac(mac)
                        s.last_seen = time.ticks_us()
                        s.configured = True   

                # Handle DATA messages
                elif msg_type == DATA_MSG:
                    if self.is_known(mac) == False:
                        e.send(mac, pack_reconnect())
                    else:
                        s = self.get_by_mac(mac)
                        s.last_seen = time.ticks_us()
                        # Store data in slave instance. Main task will Process data.
                        s.set_data(dict)
                        print("Data from", binascii.hexlify(mac, ':'), ":", dict)

                # Handle Unknown messages
                else:
                    e.send(mac, pack_reconnect())
                    print("Unknown message type from", binascii.hexlify(mac, ':'), "msg:", msg)        
    
class BMSSlave(Slaves):
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
        self.vstr = 0
        
    def configure(self, e):
        e.send(self.mac, pack_config_msg(self.bal_start_voltage, self.bal_threshold,self.ext_bal_en,self.bal_en))

    def set_data(self,dict):
        vcell, vstr, temp = unpack_data_msg(dict)
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

    def set_info(self, dict):
        s_addr, ncell, ntemp, fw_ver, hw_ver= unpack_hello_msg(dict)
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
