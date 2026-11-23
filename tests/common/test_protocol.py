"""Protocol codec tests T01–T07, T10, T11 (docs/protocol.md 9.1)."""

import json
import os
import pathlib
import struct
import zlib

import pytest

from common import protocol as p
from common.crc import crc32, crc32_py

NET = 0x1234
VECTORS = pathlib.Path(__file__).with_name("vectors_v1.json")

DEFAULT_PARAMS = ((1, 16), (2, 4), (3, 1000), (4, 100), (5, 36500), (6, 35500), (7, 28000), (8, 25000), (9, 500),
                  (10, 0), (11, 450), (12, -100), (13, 550), (14, 50), (15, 850), (16, 30000), (17, 30000), (18, 1),
                  (19, 0), (20, 34000), (21, 100), (22, 1000), (23, 0))

SAMPLES = {
    "sync": (p.SYNC, p.ADDR_ALL, p.Sync(123456789, 1000, p.M_CONNECTED, 0, 7, 0xDEADBEEF, p.BAL_MASTER, 33500, 600,
                                        (0x0001, 0x8000, 0, 0, 0x00F0, 0, 0, 0, 0, 0xFFFF))),
    "config": (p.CONFIG, 3, p.Config(7, p.config_crc(DEFAULT_PARAMS), DEFAULT_PARAMS)),
    "command": (p.COMMAND, 3, p.Command(p.CMD_GET_LOG, 42, bytes((0, 10)))),
    "hello": (p.HELLO, 3, p.Hello(p.VER, (4, 0, 1), 40, p.S_SEARCH, 1, 0x00FF, 7, 0xDEADBEEF, 3600, p.HELLO_PAIRED)),
    "data": (p.DATA, 3, p.Data(123456000, p.S_RUN, p.F_TEMP_MISSING, -2, p.module_raw(52.123), 0x0003, 66,
                               (215, 220, 231, p.TEMP_NA, 348, 302),
                               tuple(p.cell_raw(3.3 + i * 0.0011) for i in range(16)))),
    "event": (p.EVENT, 3, p.Event(123456321, (p.EventItem(p.EV_CELL_OV_WARN, 5, 35512, 35500, 1),
                                              p.EventItem(p.EV_FAULT + 4, 2, 0, 0, 1)))),
    "config_ack": (p.CONFIG_ACK, 3, p.ConfigAck(7, 0xDEADBEEF, p.CFG_RANGE, 6)),
    "response": (p.RESPONSE, 3, p.Response(p.CMD_GET_LOG, 42, 0, bytes(range(24)))),
}


def frame(name, net_id=NET, session=5, seq=100):
    msg_type, addr, msg = SAMPLES[name]
    return p.encode(msg_type, net_id, addr, session, seq, msg)


def with_crc(body):
    return body + struct.pack("<I", zlib.crc32(body))


# T01 round trip, typical and extreme values
EXTREMES = [
    (p.SYNC, p.Sync(0, 500, 0, 0, 0, 0, p.BAL_OFF, 0, 0, ())),
    (p.SYNC, p.Sync(0xFFFFFFFF, 0xFFFF, 0xFF, 0xFF, 0xFFFF, 0xFFFFFFFF, 0xFF, 0xFFFF, 0xFFFF, (0xFFFF,) * 10)),
    (p.DATA, p.Data(0, 0, 0, -32768, 0, 0, 0, (), (0,) * 4)),
    (p.DATA, p.Data(0xFFFFFFFF, 0xFF, 0xFFFFFFFF, 32767, 0xFFFF, 0xFFFF, 100, (32767,) * 6, (65535,) * 16)),
    (p.CONFIG, p.Config(0, 0, ())),
    (p.CONFIG, p.Config(1, 2, ((255, -0x80000000), (254, 0x7FFFFFFF)))),
    (p.COMMAND, p.Command(p.CMD_REBOOT, 0, b"")),
    (p.EVENT, p.Event(0, ())),
    (p.RESPONSE, p.Response(0, 0, 0, b"")),
]


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_round_trip_samples(name):
    msg_type, addr, msg = SAMPLES[name]
    hdr, decoded = p.decode(frame(name), net_id=NET)
    assert decoded == msg
    assert hdr == p.Header(p.VER, msg_type, NET, addr, 5, 100)


@pytest.mark.parametrize("msg_type,msg", EXTREMES)
def test_round_trip_extremes(msg_type, msg):
    assert p.decode(p.encode(msg_type, 0xFFFF, 0, 0xFF, 0xFFFF, msg))[1] == msg


# T02 scaling and range checks
def test_cell_voltage_resolution():
    for i in range(0, 65536, 7):
        volts = i / 10000 + 0.00003
        assert abs(p.cell_volts(p.cell_raw(volts)) - volts) <= 0.00005
    assert p.temp_celsius(p.temp_raw(None)) is None
    assert p.module_volts(p.module_raw(58.4)) == pytest.approx(58.4, abs=0.001)


@pytest.mark.parametrize("cells", [(65536,), (-1,)])
def test_out_of_range_values_rejected(cells):
    msg = SAMPLES["data"][2]._replace(cells=cells)
    with pytest.raises(ValueError):
        p.encode(p.DATA, NET, 3, 0, 0, msg)


def test_wrong_record_for_type_rejected():
    with pytest.raises(ValueError):
        p.encode(p.DATA, NET, 3, 0, 0, SAMPLES["hello"][2])


# T03 maximum sizes
def test_maximum_sizes_fit():
    largest = [
        (p.DATA, SAMPLES["data"][2]),
        (p.CONFIG, SAMPLES["config"][2]),
        (p.SYNC, SAMPLES["sync"][2]),
        (p.EVENT, p.Event(0, (p.EventItem(1, 1, 1, 1, 1),) * 16)),
        (p.RESPONSE, p.Response(0, 0, 0, bytes(p.MAX_PAYLOAD - 3))),
    ]
    for msg_type, msg in largest:
        assert len(p.encode(msg_type, NET, 3, 0, 0, msg)) <= p.MAX_FRAME
    assert len(frame("data")) == 74
    with pytest.raises(ValueError):
        p.encode(p.RESPONSE, NET, 3, 0, 0, p.Response(0, 0, 0, bytes(p.MAX_PAYLOAD - 2)))


# T04 corruption
def test_every_single_bit_flip_rejected():
    good = frame("data")
    for i in range(len(good) * 8):
        bad = bytearray(good)
        bad[i // 8] ^= 1 << (i % 8)
        with pytest.raises(p.ProtocolError) as e:
            p.decode(bytes(bad), net_id=NET)
        assert e.value.code == p.E_CRC


def test_crc_fallback_matches_native():
    data = bytes(range(256)) * 3
    assert crc32_py(data) == zlib.crc32(data) == crc32(data)


# T05 length
def test_truncated_frames_rejected():
    good = frame("data")
    for n in range(len(good)):
        with pytest.raises(p.ProtocolError) as e:
            p.decode(good[:n], net_id=NET)
        assert e.value.code == (p.E_LENGTH if n < p.HDR_LEN + p.CRC_LEN else p.E_CRC)
    with pytest.raises(p.ProtocolError) as e:
        p.decode(bytes(251))
    assert e.value.code == p.E_LENGTH


def test_short_payload_with_valid_crc_rejected():
    good = frame("data")
    body = good[:-p.CRC_LEN]
    for cut in range(1, len(body) - p.HDR_LEN):
        with pytest.raises(p.ProtocolError) as e:
            p.decode(with_crc(body[:-cut]))
        assert e.value.code == p.E_PAYLOAD
        assert e.value.header.type == p.DATA


# T06 foreign and incompatible frames
def test_net_id_address_and_major_version_checks():
    with pytest.raises(p.ProtocolError) as e:
        p.decode(frame("data"), net_id=NET + 1)
    assert e.value.code == p.E_NET_ID
    p.decode(frame("data"), net_id=None)  # pairing: any network

    p.decode(frame("command"), addr=3)
    p.decode(frame("sync"), addr=3)  # broadcast
    with pytest.raises(p.ProtocolError) as e:
        p.decode(frame("command"), addr=4)
    assert e.value.code == p.E_ADDR

    body = bytearray(frame("hello")[:-p.CRC_LEN])
    body[0] = (p.VER_MAJOR + 1) << 4
    with pytest.raises(p.ProtocolError) as e:
        p.decode(with_crc(bytes(body)), net_id=NET)
    assert e.value.code == p.E_VERSION
    assert e.value.header.addr == 3  # the master can still show which slave is incompatible


# T07 forward compatibility within a major version
def test_newer_minor_version_with_extra_fields_accepted():
    for name in SAMPLES:
        body = bytearray(frame(name)[:-p.CRC_LEN])
        body[0] = p.VER + 1
        hdr, msg = p.decode(with_crc(bytes(body)), net_id=NET)
        if SAMPLES[name][0] not in (p.COMMAND, p.RESPONSE):  # their last field takes the rest of the payload
            body += b"\x01\x02\x03"
            hdr, msg = p.decode(with_crc(bytes(body)), net_id=NET)
            assert msg == SAMPLES[name][2]
        assert hdr.ver == p.VER + 1


def test_unknown_type_rejected_with_header():
    body = bytearray(frame("data")[:-p.CRC_LEN])
    body[1] = 0x7F
    with pytest.raises(p.ProtocolError) as e:
        p.decode(with_crc(bytes(body)))
    assert e.value.code == p.E_TYPE
    assert e.value.header.type == 0x7F


# T10 configuration checksum
def test_config_crc_independent_of_order_and_sensitive_to_values():
    shuffled = tuple(reversed(DEFAULT_PARAMS))
    assert p.config_crc(shuffled) == p.config_crc(DEFAULT_PARAMS)
    changed = ((5, 36400),) + DEFAULT_PARAMS[1:]
    assert p.config_crc(changed) != p.config_crc(DEFAULT_PARAMS)
    assert set(dict(DEFAULT_PARAMS)) == set(p.PARAMS)


# T11 golden vectors: the wire format must not change unnoticed
def test_golden_vectors():
    current = {name: frame(name).hex() for name in sorted(SAMPLES)}
    if os.environ.get("UPDATE_VECTORS"):
        VECTORS.write_text(json.dumps(current, indent=1) + "\n", encoding="utf-8")
    stored = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert current == stored
    for name, hexframe in stored.items():
        assert p.decode(bytes.fromhex(hexframe), net_id=NET)[1] == SAMPLES[name][2]
    # header layout written out by hand (docs/protocol.md 3.1): ver, type, net_id, addr, session, seq
    assert stored["sync"][:16] == "1001" + "3412" + "ff" + "05" + "6400"
