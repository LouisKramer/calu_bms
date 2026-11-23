"""Sequence filter test T08 (docs/protocol.md 3.4)."""

from common.seqfilter import SeqCounter, SeqFilter

MAC = b"\x01\x02\x03\x04\x05\x06"


def test_in_order_gap_duplicate_and_old():
    f = SeqFilter()
    assert f.accept(MAC, 1, 10)
    assert f.accept(MAC, 1, 11)
    assert f.accept(MAC, 1, 20)  # gap: unicasts to other slaves are not seen
    assert not f.accept(MAC, 1, 20)  # duplicate
    assert not f.accept(MAC, 1, 15)  # older
    assert f.accept(b"\x00" * 6, 1, 15)  # other sender, own counter


def test_wrap_and_session_change():
    f = SeqFilter()
    assert f.accept(MAC, 7, 65535)
    assert f.accept(MAC, 7, 0)
    assert not f.accept(MAC, 7, 65535)
    assert f.accept(MAC, 8, 1)  # sender rebooted
    assert not f.accept(MAC, 8, 1)


def test_counter_wraps():
    c = SeqCounter(300)
    assert c.session == 300 & 0xFF
    c.seq = 65534
    assert (c.next(), c.next()) == (65535, 0)
