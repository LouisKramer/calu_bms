# common.py
from time import ticks_us, ticks_diff
import json
import struct

default_slave_cfg = {
    'balancing_start_voltage': 3.4,
    'balancing_threshold': 0.01,      # 10 mV
    'balancing_en': True,
    'balancing_ext_en': False,
    'ttl': 3600,
    'sync_interval': 10
}

def validate_slave_cfg(cfg):
    """Validate slave configuration parameters."""
    errors = []
    
    if not isinstance(cfg.get('balancing_start_voltage'), (int, float)) or not (3.0 <= cfg['balancing_start_voltage'] <= 4.0):
        errors.append("balancing_start_voltage must be between 3.0 and 4.0")
    
    if not isinstance(cfg.get('balancing_threshold'), (int, float)) or not (0.0 <= cfg['balancing_threshold'] <= 1.0):
        errors.append("balancing_threshold must be between 0.0 and 1.0")
    
    if not isinstance(cfg.get('balancing_en'), bool):
        errors.append("balancing_en must be a boolean")
    
    if not isinstance(cfg.get('balancing_ext_en'), bool):
        errors.append("balancing_ext_en must be a boolean")
    
    if not isinstance(cfg.get('ttl'), int) or cfg['ttl'] <= 0:
        errors.append("ttl must be a positive integer")
    
    if not isinstance(cfg.get('sync_interval'), (int, float)) or cfg['sync_interval'] <= 0:
        errors.append("sync_interval must be a positive number")
    
    return errors if errors else None


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
    'sampling_interval': 5.0
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

class info_data:
    def __init__(self, addr: int = 0, ncell: int = 0, ntemp: int = 0,
                 fw_ver: str = "0.0.0.0", hw_ver: str = "0.0.0.0"):
        self.addr    = addr
        self.ncell   = ncell
        self.ntemp   = ntemp
        self.fw_ver  = fw_ver
        self.hw_ver  = hw_ver

# -------------------------------------------------
# Communication Packages
# -------------------------------------------------
RECONECT_MSG = 0
SEARCH_MSG   = 1
HELLO_MSG    = 2
WELCOME_MSG  = 3
DATA_MSG     = 4
DATA_REQ_MSG = 5
CONF_MSG     = 6
CONF_ACK_MSG = 7
SYNC_REQ_MSG = 8 # Request from master to slave
SYNC_ACK_MSG = 9  # Ack from slave to master
SYNC_REF_MSG = 10 # Reference from master to slave
SYNC_FIN_MSG = 11 # Final ack from slave to master

BROADCAST = b'\xff\xff\xff\xff\xff\xff'

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
# Data messages
# -------------------------------------------------
def pack_data_msg(vcell,vstr,temp):
    return struct.pack('<B32f2f4f', DATA_MSG, *vcell, *vstr, *temp)

def unpack_data_msg(msg):
    values = struct.unpack('<B32f2f4f', msg)
    vcell = values[1:32]
    vstr  = values[32:34]
    temp  = values[34:38]
    return vcell, vstr, temp

def pack_data_req_msg(vcell, vstr, temp):
    return struct.pack('<B', DATA_REQ_MSG)


def unpack_data_req_msg():
    return 

# -------------------------------------------------
# Configuration messages
# -------------------------------------------------
def pack_config_msg(bal_start_voltage, bal_threshold, ext_bal_en, bal_en):
    return struct.pack('<BB2f2?', CONF_MSG, bal_start_voltage, bal_threshold, bal_en, ext_bal_en)

def unpack_config_msg(msg):
    value = struct.unpack('<BB2f2?', msg)
    bal_start_voltage = value[1]
    bal_threshold = value[2]
    bal_en = value[3]
    ext_bal_en = value[4]
    return bal_start_voltage, bal_threshold, ext_bal_en, bal_en

def pack_conf_ack():
    return struct.pack('<B', CONF_ACK_MSG)

def unpack_conf_ack():
    return
# -------------------------------------------------
# Discover/connect messages
# -------------------------------------------------


def pack_reconnect():
    return struct.pack('<B', RECONECT_MSG)