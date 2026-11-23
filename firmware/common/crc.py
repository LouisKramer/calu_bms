"""CRC-32 (IEEE 802.3, same result as binascii.crc32 / zlib.crc32)."""

try:
    from binascii import crc32 as _native
except ImportError:  # MicroPython builds without MICROPY_PY_BINASCII_CRC32
    _native = None

_table = None


def crc32_py(data, crc=0):
    """Table-driven fallback, used when the firmware has no native crc32."""
    global _table
    if _table is None:
        _table = []
        for i in range(256):
            c = i
            for _ in range(8):
                c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
            _table.append(c)
    crc ^= 0xFFFFFFFF
    for b in data:
        crc = _table[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def crc32(data, crc=0):
    if _native is not None:
        return _native(data, crc) & 0xFFFFFFFF
    return crc32_py(data, crc)
