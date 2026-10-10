"""Build synthetic chunks and files for tests, from the format note alone.

Nothing here is copied from a card. The checksums are computed with the library's own routines,
and test_crc.py checks those against an independent bit-by-bit implementation.
"""

from __future__ import annotations

import struct

from dreamstation.crc import crc32_words, header_checksum

SESSION_START = 1_700_000_000  # 2023-11-14T22:13:20Z


def chunk(kind: int, session: int, timestamp: int, sizes: dict[int, int], data: bytes) -> bytes:
    """A version-3 chunk: fixed header, header block, checksum, data, CRC."""
    header_block = b"".join(bytes((code, size)) for code, size in sizes.items())
    body_len = len(data) + 4
    block_size = 15 + 1 + len(header_block) + 1 + body_len
    fixed = struct.pack("<BHBBBBII", 3, block_size, 0, 0, 6, kind, session, timestamp)
    head = fixed + bytes((len(sizes),)) + header_block
    return head + bytes((header_checksum(head),)) + data + struct.pack("<I", crc32_words(data))


SUMMARY_SIZES = {0: 1, 1: 54, 2: 9, 3: 4, 4: 2, 5: 4, 6: 1, 7: 4, 8: 31, 9: 2, 10: 4, 11: 11, 12: 1}
EVENT_SIZES = {
    0: 2, 1: 3, 2: 4, 3: 3, 4: 3, 5: 3, 6: 3, 7: 3, 8: 3, 9: 2, 10: 3, 11: 4, 12: 3, 13: 2,
    14: 5, 15: 5, 16: 5, 17: 5, 18: 4, 19: 3, 20: 3, 21: 3,
}  # fmt: skip


def settings_record(
    mode: int = 2,
    pressure_min: int = 100,
    pressure_max: int = 130,
    humidifier: tuple[int, int] = (0x8C, 0x6C),
    tubing: int = 1,
    extra: bytes = b"",
) -> bytes:
    """An auto-CPAP settings record like the surveyed device writes, padded to 54 bytes."""
    items = [
        (0x00, bytes((mode,))),
        (0x01, bytes((0x03, 0x20))),
        (0x0D, bytes((pressure_min, pressure_max))),
        (0x2B, bytes((0x80,))),
        (0x2C, bytes((5,))),
        (0x2D, bytes((pressure_min,))),
        (0x2E, bytes((0x80,))),
        (0x2F, bytes((0,))),
        (0x30, bytes((3,))),
        (0x35, bytes(humidifier)),
        (0x36, bytes((0,))),
        (0x38, bytes((0,))),
        (0x39, bytes((0,))),
        (0x40, bytes((tubing,))),
        (0x3C, bytes((0,))),
        (0x3E, bytes((0x80,))),
        (0x3F, bytes((0,))),
    ]
    # Make room for ``extra`` by dropping trailing flag settings; the record size is fixed at 54.
    while sum(2 + len(v) for _, v in items) + len(extra) > 54:
        items.pop()
    body = b"".join(bytes((code, len(v))) + v for code, v in items) + extra
    # The device pads with nothing; the record size is fixed by the header block, so pad with
    # a harmless repeated flag setting to reach 54 bytes.
    while len(body) < 54:
        body += bytes((0x3F, 1, 0)) if 54 - len(body) >= 3 else b"\x00" * (54 - len(body))
    return body[:54]


def statistics_record(
    oa=0, ca=0, hy=0, rera=0, fl=0, snores=0, ll_min=0, pb_min=0, vb_min=0
) -> bytes:
    words = [0, oa, 0, ca, vb_min, ll_min, pb_min, snores, hy, 0, rera, fl, 10000, 70, 0x0E00]
    return struct.pack("<15H", *words) + bytes((50,))


def summary_data(
    *,
    mask_on_at: int = 0,
    mask_off_after: int = 7200,
    off_after: int = 0,
    settings: bytes | None = None,
    stats: bytes | None = None,
    pressure: tuple[int, int, int, int] = (100, 125, 110, 103),
    humidifier: tuple[int, int] = (0x8C, 0x6C),
) -> bytes:
    """A summary data block with one mask-on span, on at ``mask_on_at`` for ``mask_off_after``."""
    settings = settings if settings is not None else settings_record()
    stats = stats if stats is not None else statistics_record()
    return (
        bytes((0, 1))
        + bytes((1,)) + settings
        + bytes((3,)) + struct.pack("<H", mask_on_at) + bytes(humidifier)
        + bytes((5,)) + bytes(pressure)
        + bytes((4,)) + struct.pack("<H", mask_off_after)
        + bytes((8,)) + stats
        + bytes((2,)) + struct.pack("<H", off_after) + bytes(7)
    )  # fmt: skip


def ev(code: int, elapsed: int, *data: int) -> bytes:
    """One events record: code, 16-bit elapsed seconds, data bytes padded to the record size."""
    size = EVENT_SIZES[code]
    payload = struct.pack("<H", elapsed) + bytes(data)
    assert len(payload) <= size, (code, len(payload), size)
    return bytes((code,)) + payload + bytes(size - len(payload))


def summary_file(
    session: int = 0x10, timestamp: int = SESSION_START, data: bytes | None = None
) -> bytes:
    return chunk(1, session, timestamp, SUMMARY_SIZES, data if data is not None else summary_data())


def events_file(session: int = 0x10, timestamp: int = SESSION_START, data: bytes = b"") -> bytes:
    return chunk(2, session, timestamp, EVENT_SIZES, data)
