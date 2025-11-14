# common.py
from time import ticks_us, ticks_diff
import json

SYNC_REQ_FMT = "<IQ"
ACK_FMT      = "<QQ"
REF_FMT      = "<QQQ"

RECONECT_MSG = "I DONT KNOW YOU ANYMORE"
HELLO_MSG    = "I NEED A MASTER"
WELCOME_MSG  = "LET ME BE YOUR MASTER"
DATA_MSG     = "DATA"
CONF_MSG     = "CONF"
CONF_ACK_MSG = "CONF_ACK"
SYNC_REQ_MSG = "LET US ALL BE IN SYNC"
SYNC_ACK_MSG = "YES LETS SYNC"
SYNC_REF_MSG = "FINALY WE ARE IN SYNC"
SYNC_FIN_MSG = "YES FINALLY SYNCED"

BROADCAST = b''

SYNC_DEADLINE = 200_000 # 200ms

config_soc = {
    'capacity_ah': 100.0,
    'initial_soc': 80.0,
    'cell_ir': 0.004,           # 4 mΩ at 25°C
    'ir_ref_temp': 25.0,
    'ir_temp_coeff': 0.004,        # 0.4%/°C
    'current_threshold': 1.0,
    'voltage_stable_threshold': 0.01,
    'relaxed_hold_time': 30.0,
    'sampling_interval': 1.0
}


config_prot = {
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

def pack_reconnect():
    dict = {"type": RECONECT_MSG}
    return json.dumps(dict)

def pack_sync_req(T1):
    dict = {"type": SYNC_REQ_MSG, "T1":T1}
    return json.dumps(dict)

def unpack_sync_req(dict):
    T1 = dict.get("T1")
    return T1

def pack_sync_ack(T1, T2):
    dict = {"type": SYNC_ACK_MSG, "T1":T1, "T2":T2}
    return json.dumps(dict)

def unpack_sync_req(dict):
    T1 = dict.get("T1")
    T2 = dict.get("T2")
    return T1, T2

def pack_sync_ref(T1, T2, T3):
    dict = {"type": SYNC_REF_MSG, "T1":T1, "T2":T2, "T3":T3}
    return json.dumps(dict)

def unpack_sync_ref(dict):
    T1 = dict.get("T1")
    T2 = dict.get("T2")
    T3 = dict.get("T3")
    return T1, T2, T3

def pack_sync_fin(T1, T2, T3, T4):
    dict = {"type": SYNC_FIN_MSG, "T1":T1, "T2":T2, "T3":T3, "T4":T4}
    return json.dumps(dict)

def pack_config_msg(bal_start_voltage, bal_threshold, ext_bal_en, bal_en):
    dict = {"type": CONF_MSG, 
            "bal_start_vol":bal_start_voltage, 
            "bal_th":bal_threshold,
            "bal_en": bal_en,
            "ext_bal_en": ext_bal_en}
    return json.dumps(dict)

def pack_data_msg(vcell, vstr, temp):
    dict = {"type": CONF_MSG, 
            "vcell":vcell, 
            "vstr":vstr,
            "temp": temp}
    return json.dumps(dict)

def unpack_data_msg(dict):
    vcell = dict.get("vcell")
    vstr = dict.get("vstr")
    temp = dict.get("temp")
    return vcell, vstr, temp

def pack_hello_msg(slv_position, ncell, ntemp, fw_ver, hw_ver):
    dict = {"type": HELLO_MSG, 
            "slv_pos":slv_position, 
            "ncell":ncell,
            "ntemp": ntemp,
            "fw_ver": fw_ver,
            "hw_ver": hw_ver}
    return json.dumps(dict)

def unpack_hello_msg(dict):
    s_addr = dict.get("str_addr")
    ncell = dict.get("ncell")
    ntemp = dict.get("ntemp")
    fw_ver = dict.get("fw_ver")
    hw_ver = dict.get("hw_ver")
    return s_addr, ncell, ntemp, fw_ver, hw_ver

