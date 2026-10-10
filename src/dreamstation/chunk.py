"""The chunk container shared by every file on the card.

A chunk is a 15-byte fixed header, a header block of (code, size) pairs, an 8-bit header
checksum, a data block, and a CRC-32 of the data block. See docs/FORMAT.md, "The chunk
container". This module verifies both checks and hands back the data block with the record
sizes; it knows nothing about what the records mean.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .errors import FormatError

SUMMARY = 1
EVENTS = 2
WAVEFORM = 5

_FIXED = struct.Struct(
    "<BHBBBBII"
)  # version, block size, header type, family, family version, kind, session, timestamp


@dataclass(frozen=True)
class Chunk:
    """One verified chunk: its header fields and its data block."""

    path: str
    offset: int
    version: int
    header_type: int
    family: int
    family_version: int
    kind: int
    session: int
    timestamp: int
    sizes: dict[int, int] = field(repr=False)
    data: bytes = field(repr=False)

    def record_size(self, code: int) -> int:
        """The size of records with ``code`` in this chunk's data block."""
        try:
            return self.sizes[code]
        except KeyError:
            raise FormatError(
                f"record code {code:#04x} has no size in the header block",
                path=self.path,
                session=self.session,
            ) from None


def parse_chunks(raw: bytes, path: str = "<bytes>") -> list[Chunk]:
    """Split a file's bytes into verified chunks.

    Raises FormatError on a truncated chunk, an unknown format version, a header checksum or
    CRC mismatch, or a waveform header, which this library does not read.
    """
    from .crc import crc32_words, header_checksum

    chunks: list[Chunk] = []
    pos = 0
    while pos < len(raw):
        if len(raw) - pos < _FIXED.size:
            raise FormatError(f"trailing {len(raw) - pos} bytes are not a chunk", path=path)
        version, block_size, header_type, family, family_version, kind, session, timestamp = (
            _FIXED.unpack_from(raw, pos)
        )
        if version != 3:
            raise FormatError(
                f"chunk format version {version}; only version 3 is read",
                path=path,
                session=session,
            )
        if header_type != 0:
            raise FormatError(
                f"header type {header_type}; waveform chunks are not read",
                path=path,
                session=session,
            )
        if block_size < _FIXED.size + 1 + 1 + 4 or pos + block_size > len(raw):
            raise FormatError(
                f"block size {block_size} does not fit the file", path=path, session=session
            )
        count = raw[pos + _FIXED.size]
        hb_start = pos + _FIXED.size + 1
        hb_end = hb_start + 2 * count
        sum_at = hb_end
        if sum_at >= pos + block_size - 4:
            raise FormatError("header block runs past the chunk", path=path, session=session)
        sizes = {raw[i]: raw[i + 1] for i in range(hb_start, hb_end, 2)}
        if len(sizes) != count:
            raise FormatError("header block repeats a record code", path=path, session=session)
        if header_checksum(raw[pos:sum_at]) != raw[sum_at]:
            raise FormatError("header checksum mismatch", path=path, session=session)
        data = raw[sum_at + 1 : pos + block_size - 4]
        (stored_crc,) = struct.unpack_from("<I", raw, pos + block_size - 4)
        if crc32_words(data) != stored_crc:
            raise FormatError("data CRC mismatch", path=path, session=session)
        chunks.append(
            Chunk(
                path=path,
                offset=pos,
                version=version,
                header_type=header_type,
                family=family,
                family_version=family_version,
                kind=kind,
                session=session,
                timestamp=timestamp,
                sizes=sizes,
                data=data,
            )
        )
        pos += block_size
    return chunks


def records(chunk: Chunk):
    """Yield (code, payload) for each record in the chunk's data block, in order."""
    data = chunk.data
    pos = 0
    while pos < len(data):
        code = data[pos]
        size = chunk.record_size(code)
        end = pos + 1 + size
        if end > len(data):
            raise FormatError(
                f"record {code:#04x} at {pos} runs past the data block",
                path=chunk.path,
                session=chunk.session,
            )
        yield code, data[pos + 1 : end]
        pos = end
