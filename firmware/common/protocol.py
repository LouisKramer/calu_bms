"""ESP-NOW master–slave protocol v1.0 – frame and message codec (docs/protocol.md).

Pure Python for MicroPython and CPython. Messages are namedtuples holding raw integer units
(cell voltage 0.1 mV, module voltage 2 mV, temperature 0.1 °C, time ms); see the conversion helpers at the end.
"""

import struct
from collections import namedtuple

from common.crc import crc32

VER_MAJOR = 1
VER_MINOR = 0
VER = (VER_MAJOR << 4) | VER_MINOR

MAX_FRAME = 250
HDR_LEN = 8
CRC_LEN = 4
MAX_PAYLOAD = MAX_FRAME - HDR_LEN - CRC_LEN
ADDR_MASTER = 0
ADDR_ALL = 0xFF

# message types
SYNC = 0x01
CONFIG = 0x02
COMMAND = 0x03
HELLO = 0x81
DATA = 0x82
EVENT = 0x83
CONFIG_ACK = 0x84
RESPONSE = 0x85

# decode error codes
E_LENGTH = 1
E_CRC = 2
E_VERSION = 3
E_NET_ID = 4
E_ADDR = 5
E_TYPE = 6
E_PAYLOAD = 7

# slave states
S_INIT, S_SEARCH, S_CONFIG, S_RUN, S_FAULT, S_LOW_POWER = 0, 1, 2, 3, 4, 5
# master states
M_INIT, M_STANDBY, M_PRECHARGE, M_CONNECTED, M_DERATED, M_FAULT, M_SERVICE, M_SNIFF, M_LOW_POWER = range(9)

# SYNC flags
SYNC_PAIRING_OPEN = 0x01
SYNC_LOW_POWER = 0x02
SYNC_MEASURE_NOW = 0x04
# balancing modes
BAL_OFF, BAL_MASTER, BAL_SLAVE = 0, 1, 2
# HELLO flags
HELLO_VERSION_MISMATCH = 0x01
HELLO_PAIRED = 0x02
HELLO_ADDR_CONFLICT = 0x04

# commands
CMD_IDENTIFY, CMD_REBOOT, CMD_SELF_TEST, CMD_GET_LOG, CMD_CLEAR_LOG, CMD_PAIR_ACCEPT, CMD_UNPAIR, CMD_GET_HELLO = range(1, 9)
# CONFIG_ACK results
CFG_OK, CFG_CRC_ERROR, CFG_RANGE, CFG_CROSS_CHECK, CFG_MISSING, CFG_STORAGE = range(6)

# fault bits (DATA.faults, SWS-013)
F_OPEN_TAP = 1 << 0
F_CELL_RANGE = 1 << 1
F_PLAUSIBILITY = 1 << 2
F_UNUSED_TAP = 1 << 3
F_TEMP_MISSING = 1 << 4
F_TEMP_FAULTY = 1 << 5
F_BOARD_OVERTEMP = 1 << 6
F_STUCK_TAP = 1 << 7
F_ADC = 1 << 8
F_SUPPLY = 1 << 9
F_CALIBRATION = 1 << 10
F_CONFIG = 1 << 11
F_ADDRESS = 1 << 12
F_VERSION = 1 << 13
F_BAL_STOPPED = 1 << 14
F_WATCHDOG_RESET = 1 << 15

# event codes; fault bit n is reported as EV_FAULT + n
EV_CELL_OV_WARN, EV_CELL_OV_TRIP, EV_CELL_UV_WARN, EV_CELL_UV_TRIP = 1, 2, 3, 4
EV_T_CHARGE_LOW, EV_T_CHARGE_HIGH, EV_T_DISCHARGE_LOW, EV_T_DISCHARGE_HIGH, EV_T_BOARD_HIGH = 5, 6, 7, 8, 9
EV_FAULT = 0x40

# slave configuration parameters: id -> (name, raw units per engineering unit)
PARAMS = {
    1: ("cells_per_module", 1), 2: ("temp_sensor_count", 1), 3: ("meas_period", 1000), 4: ("plaus_tol", 100),
    5: ("cell_ov_trip", 10000), 6: ("cell_ov_warn", 10000), 7: ("cell_uv_warn", 10000), 8: ("cell_uv_trip", 10000),
    9: ("cell_v_hyst", 10000), 10: ("t_charge_min", 10), 11: ("t_charge_max", 10), 12: ("t_discharge_min", 10),
    13: ("t_discharge_max", 10), 14: ("t_trip_margin", 10), 15: ("t_board_max", 10), 16: ("slave_timeout_trip", 1000),
    17: ("slave_bal_timeout", 1000), 18: ("bal_passive_en", 1), 19: ("bal_active_en", 1), 20: ("bal_start_v", 10000),
    21: ("bal_delta", 10000), 22: ("bal_active_freq", 1), 23: ("espnow_channel", 1),
}

Header = namedtuple("Header", ("ver", "type", "net_id", "addr", "session", "seq"))
Sync = namedtuple("Sync", ("net_time", "meas_period", "master_state", "flags", "cfg_version", "cfg_crc", "bal_mode",
                           "bal_target", "lp_period", "bal_masks"))
Config = namedtuple("Config", ("cfg_version", "cfg_crc", "params"))
Command = namedtuple("Command", ("cmd", "token", "args"))
Hello = namedtuple("Hello", ("proto", "fw_version", "hw_version", "state", "reset_reason", "self_test", "cfg_version",
                             "cfg_crc", "uptime", "flags"))
Data = namedtuple("Data", ("t_meas", "state", "faults", "time_offset", "v_module", "bal_mask", "bal_duty", "temps",
                           "cells"))
EventItem = namedtuple("EventItem", ("code", "index", "value", "limit", "active"))
Event = namedtuple("Event", ("t", "events"))
ConfigAck = namedtuple("ConfigAck", ("cfg_version", "cfg_crc", "result", "param_id"))
Response = namedtuple("Response", ("cmd", "token", "result", "data"))


class ProtocolError(Exception):
    """Frame rejected; `code` is one of E_*, `header` is set when the header could be read."""

    def __init__(self, code, header=None):
        super().__init__(code)
        self.code = code
        self.header = header


_RANGE = {"B": (0, 0xFF), "H": (0, 0xFFFF), "h": (-0x8000, 0x7FFF), "I": (0, 0xFFFFFFFF),
          "i": (-0x80000000, 0x7FFFFFFF)}


def _pack(fmt, *values):
    # MicroPython's struct does not check ranges, so check here for both interpreters
    for c, v in zip(fmt, values):
        lo, hi = _RANGE[c]
        if not lo <= v <= hi:
            raise ValueError("value out of range")
    return struct.pack("<" + fmt, *values)


class _Reader:
    def __init__(self, buf):
        self.buf = buf
        self.pos = 0

    def take(self, fmt):
        size = struct.calcsize("<" + fmt)
        if self.pos + size > len(self.buf):
            raise ProtocolError(E_PAYLOAD)
        values = struct.unpack_from("<" + fmt, self.buf, self.pos)
        self.pos += size
        return values

    def rest(self):
        data = bytes(self.buf[self.pos:])
        self.pos = len(self.buf)
        return data


# ---- payload encoders ------------------------------------------------------------------------------------------

def _enc_sync(m):
    return _pack("IHBBHIBHHB", m.net_time, m.meas_period, m.master_state, m.flags, m.cfg_version, m.cfg_crc,
                 m.bal_mode, m.bal_target, m.lp_period, len(m.bal_masks)) + _pack("H" * len(m.bal_masks), *m.bal_masks)


def _enc_params(params):
    out = b""
    for pid, value in params:
        out += _pack("Bi", pid, value)
    return out


def _enc_config(m):
    return _pack("HIB", m.cfg_version, m.cfg_crc, len(m.params)) + _enc_params(m.params)


def _enc_command(m):
    return _pack("BB", m.cmd, m.token) + bytes(m.args)


def _enc_hello(m):
    return _pack("BBBBBBBHHIIB", m.proto, m.fw_version[0], m.fw_version[1], m.fw_version[2], m.hw_version, m.state,
                 m.reset_reason, m.self_test, m.cfg_version, m.cfg_crc, m.uptime, m.flags)


def _enc_data(m):
    return (_pack("IBIhHHBB", m.t_meas, m.state, m.faults, m.time_offset, m.v_module, m.bal_mask, m.bal_duty,
                  len(m.temps)) + _pack("h" * len(m.temps), *m.temps) + _pack("B", len(m.cells))
            + _pack("H" * len(m.cells), *m.cells))


def _enc_event(m):
    out = _pack("IB", m.t, len(m.events))
    for e in m.events:
        out += _pack("BBBBii", e.code, e.index, e.active, 0, e.value, e.limit)
    return out


def _enc_config_ack(m):
    return _pack("HIBB", m.cfg_version, m.cfg_crc, m.result, m.param_id)


def _enc_response(m):
    return _pack("BBB", m.cmd, m.token, m.result) + bytes(m.data)


# ---- payload decoders ------------------------------------------------------------------------------------------

def _dec_sync(r):
    v = r.take("IHBBHIBHHB")
    return Sync(*(v[:9] + (r.take("H" * v[9]),)))


def _dec_config(r):
    version, crc, count = r.take("HIB")
    params = tuple(r.take("Bi") for _ in range(count))
    return Config(version, crc, params)


def _dec_command(r):
    cmd, token = r.take("BB")
    return Command(cmd, token, r.rest())


def _dec_hello(r):
    v = r.take("BBBBBBBHHIIB")
    return Hello(*((v[0], (v[1], v[2], v[3])) + v[4:]))


def _dec_data(r):
    v = r.take("IBIhHHBB")
    temps = r.take("h" * v[7])
    n_cells = r.take("B")[0]
    return Data(*(v[:7] + (temps, r.take("H" * n_cells))))


def _dec_event(r):
    t, count = r.take("IB")
    events = []
    for _ in range(count):
        code, index, active, _reserved, value, limit = r.take("BBBBii")
        events.append(EventItem(code, index, value, limit, active))
    return Event(t, tuple(events))


def _dec_config_ack(r):
    return ConfigAck(*r.take("HIBB"))


def _dec_response(r):
    cmd, token, result = r.take("BBB")
    return Response(cmd, token, result, r.rest())


_CODEC = {
    SYNC: (Sync, _enc_sync, _dec_sync),
    CONFIG: (Config, _enc_config, _dec_config),
    COMMAND: (Command, _enc_command, _dec_command),
    HELLO: (Hello, _enc_hello, _dec_hello),
    DATA: (Data, _enc_data, _dec_data),
    EVENT: (Event, _enc_event, _dec_event),
    CONFIG_ACK: (ConfigAck, _enc_config_ack, _dec_config_ack),
    RESPONSE: (Response, _enc_response, _dec_response),
}


# ---- frames ----------------------------------------------------------------------------------------------------

def encode(msg_type, net_id, addr, session, seq, msg):
    """Build a complete frame (header + payload + CRC). Raises ValueError for invalid values or size."""
    cls, enc, _ = _CODEC[msg_type]
    if not isinstance(msg, cls):
        raise ValueError("message does not match type")
    payload = enc(msg)
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload too long")
    frame = _pack("BBHBBH", VER, msg_type, net_id, addr, session, seq) + payload
    return frame + struct.pack("<I", crc32(frame))


def decode(frame, net_id=None, addr=None):
    """Check and decode a frame (docs/protocol.md 3.2, checks 2–5 and 7).

    net_id: expected network ID (None while pairing). addr: own module address on a slave (accepts ADDR_ALL too);
    None on the master, which checks the address against its pairing table. Raises ProtocolError.
    """
    n = len(frame)
    if n < HDR_LEN + CRC_LEN or n > MAX_FRAME:
        raise ProtocolError(E_LENGTH)
    if struct.unpack_from("<I", frame, n - CRC_LEN)[0] != crc32(memoryview(frame)[:n - CRC_LEN]):
        raise ProtocolError(E_CRC)
    hdr = Header(*struct.unpack_from("<BBHBBH", frame, 0))
    if hdr.ver >> 4 != VER_MAJOR:
        raise ProtocolError(E_VERSION, hdr)
    if net_id is not None and hdr.net_id != net_id:
        raise ProtocolError(E_NET_ID, hdr)
    if addr is not None and hdr.addr != addr and hdr.addr != ADDR_ALL:
        raise ProtocolError(E_ADDR, hdr)
    codec = _CODEC.get(hdr.type)
    if codec is None:
        raise ProtocolError(E_TYPE, hdr)
    try:
        msg = codec[2](_Reader(memoryview(frame)[HDR_LEN:n - CRC_LEN]))
    except ProtocolError as e:
        e.header = hdr
        raise
    return hdr, msg


def config_crc(params):
    """CRC-32 of a parameter list, independent of its order (CFG-001)."""
    return crc32(_enc_params(sorted(params)))


# ---- unit conversion -------------------------------------------------------------------------------------------

TEMP_NA = -0x8000


def cell_raw(volts):
    return int(round(volts * 10000))


def cell_volts(raw):
    return raw / 10000


def module_raw(volts):
    return int(round(volts * 500))


def module_volts(raw):
    return raw / 500


def temp_raw(celsius):
    return TEMP_NA if celsius is None else int(round(celsius * 10))


def temp_celsius(raw):
    return None if raw == TEMP_NA else raw / 10
