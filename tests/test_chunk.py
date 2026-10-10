"""The chunk container: header fields, header block, both checks, and what is refused."""

import struct

import pytest
from build import EVENT_SIZES, SUMMARY_SIZES, chunk, summary_data

from dreamstation.chunk import parse_chunks, records
from dreamstation.errors import FormatError


def test_parses_header_and_sizes():
    raw = chunk(1, 0x528, 1_791_461_415, SUMMARY_SIZES, summary_data())
    (c,) = parse_chunks(raw, "x.001")
    assert (c.version, c.header_type, c.family, c.family_version, c.kind) == (3, 0, 0, 6, 1)
    assert c.session == 0x528
    assert c.timestamp == 1_791_461_415
    assert c.sizes == SUMMARY_SIZES
    assert c.data == summary_data()


def test_two_chunks_in_one_file():
    raw = chunk(2, 1, 10, EVENT_SIZES, b"") + chunk(2, 2, 20, EVENT_SIZES, b"")
    a, b = parse_chunks(raw)
    assert (a.session, b.session) == (1, 2)
    assert b.offset == len(raw) // 2


def test_records_walk_by_header_block_size():
    sizes = {7: 2, 9: 1}
    raw = chunk(2, 1, 0, sizes, bytes((7, 1, 2, 9, 3, 7, 4, 5)))
    (c,) = parse_chunks(raw)
    assert list(records(c)) == [(7, b"\x01\x02"), (9, b"\x03"), (7, b"\x04\x05")]


def test_record_with_unknown_code_is_refused():
    raw = chunk(2, 1, 0, {7: 2}, bytes((8, 1, 2)))
    (c,) = parse_chunks(raw, "f.002")
    with pytest.raises(FormatError, match="0x08 has no size"):
        list(records(c))


def test_record_running_past_block_is_refused():
    raw = chunk(2, 1, 0, {7: 2}, bytes((7, 1)))
    (c,) = parse_chunks(raw)
    with pytest.raises(FormatError, match="runs past"):
        list(records(c))


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda r: r[:5] + bytes((r[5] ^ 1,)) + r[6:], "header checksum"),
        (lambda r: r[:-6] + bytes((r[-6] ^ 1,)) + r[-5:], "CRC"),
        (lambda r: r[:-1], "block size"),
        (lambda r: b"\x02" + r[1:], "format version 2"),
        (lambda r: r[:3] + b"\x01" + r[4:], "waveform"),
    ],
)
def test_corruption_is_refused(mutate, message):
    raw = chunk(1, 0x10, 0, SUMMARY_SIZES, summary_data())
    with pytest.raises(FormatError, match=message):
        parse_chunks(mutate(raw), "bad.001")


def test_error_names_file_and_session():
    raw = chunk(1, 0x10, 0, SUMMARY_SIZES, summary_data())
    bad = raw[:-1] + bytes((raw[-1] ^ 1,))
    with pytest.raises(FormatError) as e:
        parse_chunks(bad, "P0/00000010.001")
    assert "P0/00000010.001" in str(e.value)
    assert "session 0x10" in str(e.value)


def test_trailing_garbage_is_refused():
    raw = chunk(2, 1, 0, EVENT_SIZES, b"") + b"\x03\x00"
    with pytest.raises(FormatError, match="trailing"):
        parse_chunks(raw)


def test_block_size_is_little_endian():
    raw = chunk(2, 1, 0, EVENT_SIZES, b"")
    assert struct.unpack_from("<H", raw, 1)[0] == len(raw)
