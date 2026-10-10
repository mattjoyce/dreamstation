"""The summary file (.001): mask on and off times, settings, pressure summary, statistics.

See docs/FORMAT.md, "The summary file".
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .chunk import SUMMARY, Chunk, records
from .errors import FormatError, UnsupportedDeviceError
from .settings import Humidifier, Settings

EQUIPMENT_ON = 0
SETTINGS = 1
EQUIPMENT_OFF = 2
MASK_ON = 3
MASK_OFF = 4
PRESSURE_SUMMARY = 5
STATISTICS = 8


@dataclass(frozen=True)
class Slice:
    """A mask-on span, in seconds from the session start."""

    start: int
    end: int
    humidifier: Humidifier | None = None

    @property
    def seconds(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class PressureSummary:
    """The device's own pressure summary for the session, tenths of cm H2O."""

    minimum: int
    maximum: int
    percentile_90: int
    mean: int


@dataclass(frozen=True)
class Statistics:
    """The device's own counts for the session (summary record 8)."""

    obstructive_apneas: int
    clear_airway_apneas: int
    hypopneas: int
    reras: int
    flow_limitations: int
    snores: int
    large_leak_minutes: int
    periodic_breathing_minutes: int
    variable_breathing_minutes: int
    unknown_words: tuple[int, ...]  # words 0, 2, 9, 12, 13, 14 and the trailing byte, in that order


@dataclass
class Summary:
    """One session's summary chunk, decoded."""

    session: int
    timestamp: int  # session start, epoch seconds UTC
    duration: int  # seconds to equipment off
    settings: Settings
    slices: list[Slice]
    pressure: PressureSummary | None
    statistics: Statistics | None
    equipment_off_bytes: bytes = field(default=b"", repr=False)


def check_family(chunk: Chunk) -> None:
    if (chunk.family, chunk.family_version) != (0, 6):
        raise UnsupportedDeviceError(
            f"family {chunk.family} version {chunk.family_version}; only DreamStation "
            "(family 0, version 6) is read",
            path=chunk.path,
            session=chunk.session,
        )


def parse_summary(chunk: Chunk) -> Summary:
    """Decode a summary chunk. Stops on any record code the format note does not describe."""
    check_family(chunk)
    if chunk.kind != SUMMARY:
        raise FormatError(
            f"chunk kind {chunk.kind} is not a summary", path=chunk.path, session=chunk.session
        )
    path, sid = chunk.path, chunk.session
    settings: Settings | None = None
    pressure: PressureSummary | None = None
    stats: Statistics | None = None
    slices: list[Slice] = []
    open_slice: tuple[int, Humidifier] | None = None
    elapsed = 0
    duration: int | None = None
    off_bytes = b""
    for code, payload in records(chunk):
        if code == EQUIPMENT_ON:
            continue
        if code == SETTINGS:
            settings = Settings.from_bytes(payload, path=path, session=sid)
        elif code == MASK_ON:
            elapsed += struct.unpack_from("<H", payload)[0]
            if open_slice is not None:
                raise FormatError("mask on while already on", path=path, session=sid)
            open_slice = (elapsed, Humidifier.from_bytes(payload[2], payload[3]))
        elif code == MASK_OFF:
            elapsed += struct.unpack_from("<H", payload)[0]
            if open_slice is None:
                raise FormatError("mask off while not on", path=path, session=sid)
            slices.append(Slice(open_slice[0], elapsed, open_slice[1]))
            open_slice = None
        elif code == EQUIPMENT_OFF:
            elapsed += struct.unpack_from("<H", payload)[0]
            duration = elapsed
            off_bytes = bytes(payload[2:])
        elif code == PRESSURE_SUMMARY:
            pressure = PressureSummary(payload[0], payload[1], payload[2], payload[3])
        elif code == STATISTICS:
            if len(payload) < 31:
                raise FormatError(
                    f"statistics record of {len(payload)} bytes", path=path, session=sid
                )
            w = struct.unpack_from("<15H", payload)
            stats = Statistics(
                obstructive_apneas=w[1],
                clear_airway_apneas=w[3],
                hypopneas=w[8],
                reras=w[10],
                flow_limitations=w[11],
                snores=w[7],
                large_leak_minutes=w[5],
                periodic_breathing_minutes=w[6],
                variable_breathing_minutes=w[4],
                unknown_words=(w[0], w[2], w[9], w[12], w[13], w[14], payload[30]),
            )
        else:
            raise FormatError(
                f"summary record code {code:#04x} is not known", path=path, session=sid
            )
    if settings is None:
        raise FormatError("summary has no settings record", path=path, session=sid)
    if open_slice is not None:
        # The device turned off with the mask still on; close the slice at the end.
        end = duration if duration is not None else open_slice[0]
        slices.append(Slice(open_slice[0], end, open_slice[1]))
    if duration is None:
        raise FormatError("summary has no equipment-off record", path=path, session=sid)
    return Summary(
        session=sid,
        timestamp=chunk.timestamp,
        duration=duration,
        settings=settings,
        slices=slices,
        pressure=pressure,
        statistics=stats,
        equipment_off_bytes=off_bytes,
    )
