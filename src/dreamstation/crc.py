"""The two integrity checks a chunk carries.

The header ends in an 8-bit additive checksum. The data block ends in a CRC-32 computed MSB-first
with polynomial 0x04C11DB7, initial value 0xFFFFFFFF and no final inversion, over each data byte
widened to a 32-bit word (0, 0, 0, b). That widening is what a hardware CRC unit fed whole words
does, and it is the detail that makes a standard CRC-32 routine disagree with the card.
"""

from __future__ import annotations

_POLY = 0x04C11DB7


def _table() -> list[int]:
    table = []
    for i in range(256):
        c = i << 24
        for _ in range(8):
            c = ((c << 1) ^ _POLY) & 0xFFFFFFFF if c & 0x80000000 else (c << 1) & 0xFFFFFFFF
        table.append(c)
    return table


_TABLE = _table()


def crc32_words(data: bytes) -> int:
    """CRC-32 of ``data`` as the DreamStation computes it over a data block."""
    crc = 0xFFFFFFFF
    table = _TABLE
    for b in data:
        # Three zero bytes, then the data byte: one 32-bit word per input byte.
        for _ in range(3):
            crc = (table[(crc >> 24) & 0xFF] ^ (crc << 8)) & 0xFFFFFFFF
        crc = (table[(b ^ (crc >> 24)) & 0xFF] ^ (crc << 8)) & 0xFFFFFFFF
    return crc


def header_checksum(header: bytes) -> int:
    """The 8-bit sum of the header bytes that precede the stored checksum."""
    return sum(header) & 0xFF
