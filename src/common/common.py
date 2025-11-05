# common.py
import struct
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