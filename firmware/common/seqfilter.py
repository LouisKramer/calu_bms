"""Duplicate and out-of-order detection per sender (docs/protocol.md 3.4)."""


class SeqCounter:
    """Session and sequence number for the messages this device sends."""

    def __init__(self, session):
        self.session = session & 0xFF
        self.seq = 0

    def next(self):
        self.seq = (self.seq + 1) & 0xFFFF
        return self.seq


class SeqFilter:
    """Accepts only messages that are newer than the last accepted one of the same sender."""

    def __init__(self):
        self._last = {}

    def accept(self, peer, session, seq):
        last = self._last.get(peer)
        if last is None or last[0] != session:
            self._last[peer] = [session, seq]
            return True
        if 0 < ((seq - last[1]) & 0xFFFF) < 0x8000:
            last[1] = seq
            return True
        return False

    def forget(self, peer):
        self._last.pop(peer, None)
