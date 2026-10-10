"""The CRC-32 variant, checked against a bit-by-bit reference written from the definition."""

from dreamstation.crc import crc32_words, header_checksum


def _crc32_bitwise(words: bytes, poly=0x04C11DB7, init=0xFFFFFFFF) -> int:
    crc = init
    for b in words:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


def _reference(data: bytes) -> int:
    widened = b"".join(bytes((0, 0, 0, b)) for b in data)
    return _crc32_bitwise(widened)


def test_matches_bitwise_reference():
    for data in (b"", b"\x00", b"\xff", bytes(range(256)), b"DreamStation" * 7):
        assert crc32_words(data) == _reference(data)


def test_widening_matters():
    # A standard byte-wise CRC over the same bytes gives a different answer; the card's does not.
    data = bytes(range(32))
    assert crc32_words(data) != _crc32_bitwise(data)


def test_header_checksum_is_additive_mod_256():
    assert header_checksum(b"") == 0
    assert header_checksum(b"\xff\x02") == 1
    assert header_checksum(bytes(range(1, 11))) == 55
