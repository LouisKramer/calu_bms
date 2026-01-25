# common.py
from machine import RTC
import struct
import time


default_soc_cfg = {
    'capacity_ah': 100.0,
    'num_cells': 16,
    'initial_soc': 80.0,
    'cell_ir': 0.004,           # 4 mΩ at 25°C
    'ir_ref_temp': 25.0,
    'ir_temp_coeff': 0.004,        # 0.4%/°C
    'current_threshold': 1.0,
    'voltage_stable_threshold': 0.01,
    'relaxed_hold_time': 30.0,
    'sampling_interval': 2.0
}

default_prot_cfg = {
    'inverter_en_pin': 15,
    'max_current': 25.0,
    'charge_current_table': [
        (0, 25.0),
        (90, 25.0),
        (95, 10.0),
        (98, 5.0),
        (99, 2.0),
        (100, 0.0)
    ],
    'over_voltage_cell': 3.65,
    'under_voltage_cell': 3.00,
    'critical_under_voltage': 2.80,
    'over_temp': 60.0,
    'under_temp': 0.0,
    'soc_low_cutoff': 10.0,
    'soc_critical_cutoff': 5.0,
    'short_circuit_threshold': 120.0,
    'use_hardware_fault': True
}

config_can = {
    'can_tx_pin': 40,      # ESP32 GPIO
    'can_rx_pin': 39,
    'baudrate': 125000,    # 125 kbps
    'update_interval': 1.0
}

class battery:
    def __init__(self):
        self.info    = info_data()
        self.conf    = conf_data()
        self.meas    = None
        self.state   = status_data()
    def create_measurements(self):
        """Call this after you know ncell & ntemp"""
        self.meas = meas_data(self) 
        
class status_data:
    def __init__(self):
        self.channel_found = False
        self.com_active = False
        self.synced = False
        self.ttl = 0

class info_data:
    def __init__(self):
        self.mac        = b''
        self.master_mac = b''
        self.addr       = 0
        self.ncell      = 0
        self.ntemp      = 0
        self.fw_ver     = "0.0.0.0"
        self.hw_ver     = "0.0.0.0"
        
    def set(self, other: 'info_data'):
        if isinstance(other, info_data):
            self.mac        =    other.mac        
            self.master_mac =    other.master_mac 
            self.addr       =    other.addr       
            self.ncell      =    other.ncell      
            self.ntemp      =    other.ntemp      
            self.fw_ver     =    other.fw_ver     
            self.hw_ver     =    other.hw_ver          

class meas_data:
    def __init__(self, bat: battery):
        self.vcell = [0] * bat.info.ncell
        self.vstr = 0
        self.temps = [0] * bat.info.ntemp

class conf_data:
    def __init__(self):
        self.bal_start_vol     = 3.4
        self.bal_threshold     = 0.01      # 10 mV
        self.bal_en            = True
        self.bal_ext_en        = False
        self.ttl               = 10     # 10*30s
    def set(self, other: 'conf_data'):
        if not isinstance(other, conf_data):
            return

        # Voltage: only accept reasonable values
        if isinstance(other.bal_start_vol, (int, float)):
            if 2.8 <= other.bal_start_vol <= 3.8:  
                self.bal_start_vol = float(other.bal_start_vol)

        # Threshold: usually 5–50 mV
        if isinstance(other.bal_threshold, (int, float)):
            if 0.005 <= other.bal_threshold <= 0.100:
                self.bal_threshold = float(other.bal_threshold)

        # Booleans: accept anything truthy/falsy
        if other.bal_en is not None:
            self.bal_en = bool(other.bal_en)

        if other.bal_ext_en is not None:
            self.bal_ext_en = bool(other.bal_ext_en)
# -------------------------------------------------
# Communication Packages
# -------------------------------------------------
SYNC_REQ_MSG = 8 # Request from master to slave
SYNC_ACK_MSG = 9  # Ack from slave to master
SYNC_REF_MSG = 10 # Reference from master to slave
SYNC_FIN_MSG = 11 # Final ack from slave to master

SYNC_DEADLINE = 200_000 # 200ms

# -------------------------------------------------
# Sync messages
# -------------------------------------------------
def pack_sync_req(T1):
    return struct.pack('<BQ', SYNC_REQ_MSG, T1)

def unpack_sync_req(msg):
    T1 = struct.unpack('<BQ', msg)
    return T1

def pack_sync_ack(T1, T2):
    return struct.pack('<BQQ', SYNC_ACK_MSG, T1, T2)

def unpack_sync_ack(msg):
    value = struct.unpack('<BQQ', msg)
    T1 = value[1]
    T2 = value[2]
    return T1, T2

def pack_sync_ref(T1, T2, T3):
    return struct.pack('<BQQQ', SYNC_REF_MSG, T1, T2, T3)

def unpack_sync_ref(msg):
    value = struct.unpack('<BQQQ', msg)
    T1 = value[1]
    T2 = value[2]
    T3 = value[3]
    return T1, T2, T3

def pack_sync_fin(T1, T2, T3, T4):
    return struct.pack('<BQQQQ', SYNC_FIN_MSG, T1, T2, T3, T4)

def unpack_sync_fin(msg):
    value = struct.unpack('<BQQQQ', msg)
    T1 = value[1]
    T2 = value[2]
    T3 = value[3]
    T4 = value[4]
    return T1, T2, T3, T4

# -------------------------------------------------
# Discover/connect messages
# -------------------------------------------------
def pack_reconnect():
    return struct.pack('<B', RECONECT_MSG)