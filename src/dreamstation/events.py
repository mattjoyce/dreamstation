"""The events file (.002): respiratory events, pressure adjustments and two-minute statistics.

See docs/FORMAT.md, "The events file". Times are seconds from the session start. An event the
device reports after it ended is placed at its end minus the reported delay, as the device's own
reports place it.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .chunk import EVENTS, Chunk, records
from .errors import FormatError
from .summary import check_family

# Event kinds, by the code the device writes.
PRESSURE_SET = 0x01
BILEVEL_PRESSURE_SET = 0x02
AUTO_START_PRESSURE = 0x03
PRESSURE_PULSE = 0x04
RERA = 0x05
OBSTRUCTIVE_APNEA = 0x06
CLEAR_AIRWAY_APNEA = 0x07
HYPOPNEA_A = 0x0A
HYPOPNEA_B = 0x0B
FLOW_LIMITATION = 0x0C
VIBRATORY_SNORE = 0x0D
VARIABLE_BREATHING = 0x0E
PERIODIC_BREATHING = 0x0F
LARGE_LEAK = 0x10
INTERVAL_STATISTICS = 0x11
SNORES_AT_PRESSURE = 0x12
HYPOPNEA = 0x14
HYPOPNEA_C = 0x15

KIND_NAMES = {
    PRESSURE_SET: "pressure_set",
    BILEVEL_PRESSURE_SET: "bilevel_pressure_set",
    AUTO_START_PRESSURE: "auto_start_pressure",
    PRESSURE_PULSE: "pressure_pulse",
    RERA: "rera",
    OBSTRUCTIVE_APNEA: "obstructive_apnea",
    CLEAR_AIRWAY_APNEA: "clear_airway_apnea",
    HYPOPNEA_A: "hypopnea_variant_a",
    HYPOPNEA_B: "hypopnea_variant_b",
    FLOW_LIMITATION: "flow_limitation",
    VIBRATORY_SNORE: "vibratory_snore",
    VARIABLE_BREATHING: "variable_breathing",
    PERIODIC_BREATHING: "periodic_breathing",
    LARGE_LEAK: "large_leak",
    HYPOPNEA: "hypopnea",
    HYPOPNEA_C: "hypopnea_variant_c",
}

_MIN_SIZE = {
    PRESSURE_SET: 3,
    BILEVEL_PRESSURE_SET: 4,
    AUTO_START_PRESSURE: 3,
    PRESSURE_PULSE: 3,
    RERA: 3,
    OBSTRUCTIVE_APNEA: 3,
    CLEAR_AIRWAY_APNEA: 3,
    HYPOPNEA_A: 3,
    HYPOPNEA_B: 4,
    FLOW_LIMITATION: 3,
    VIBRATORY_SNORE: 2,
    VARIABLE_BREATHING: 5,
    PERIODIC_BREATHING: 5,
    LARGE_LEAK: 5,
    INTERVAL_STATISTICS: 5,
    SNORES_AT_PRESSURE: 4,
    HYPOPNEA: 3,
    HYPOPNEA_C: 3,
}


@dataclass(frozen=True)
class Event:
    """A respiratory event or a pressure change.

    ``time`` is seconds from the session start. ``duration`` is seconds for spans (periodic
    breathing, large leak, variable breathing) and 0 for point events. ``value`` is the pressure
    for pressure events (tenths of cm H2O; for a bi-level adjustment, EPAP, with IPAP in
    ``value2``) and the unknown byte for a pressure pulse.
    """

    kind: str
    time: int
    duration: int = 0
    value: int | None = None
    value2: int | None = None


@dataclass(frozen=True)
class IntervalStatistics:
    """The device's two-minute statistics, reported at the end of the interval."""

    time: int
    total_leak: int  # litres per minute
    snores: int
    pressure: int  # tenths of cm H2O; see FORMAT.md for what this averages


@dataclass(frozen=True)
class SnoresAtPressure:
    """Snore count at one pressure level over the session."""

    pressure_kind: str  # cpap, epap, ipap
    pressure: int
    snores: int


@dataclass
class Events:
    """One session's events chunk, decoded."""

    session: int
    timestamp: int
    duration: int  # time of the last record, seconds from the start
    events: list[Event]
    intervals: list[IntervalStatistics]
    snores_at_pressure: list[SnoresAtPressure]


_PRESSURE_KINDS = {0: "cpap", 1: "epap", 2: "ipap"}


def parse_events(chunk: Chunk) -> Events:
    """Decode an events chunk. Stops on any record code the format note does not describe."""
    check_family(chunk)
    if chunk.kind != EVENTS:
        raise FormatError(
            f"chunk kind {chunk.kind} is not events", path=chunk.path, session=chunk.session
        )
    path, sid = chunk.path, chunk.session
    t = 0
    events: list[Event] = []
    intervals: list[IntervalStatistics] = []
    snores: list[SnoresAtPressure] = []
    for code, payload in records(chunk):
        if code not in _MIN_SIZE:
            raise FormatError(f"event code {code:#04x} is not known", path=path, session=sid)
        if len(payload) < _MIN_SIZE[code]:
            raise FormatError(
                f"event {code:#04x} record of {len(payload)} bytes is too short",
                path=path,
                session=sid,
            )
        if code == SNORES_AT_PRESSURE:
            kind = payload[0]
            if kind not in _PRESSURE_KINDS:
                raise FormatError(f"snore pressure kind {kind}", path=path, session=sid)
            snores.append(
                SnoresAtPressure(
                    _PRESSURE_KINDS[kind], payload[1], struct.unpack_from("<H", payload, 2)[0]
                )
            )
            continue
        t += struct.unpack_from("<H", payload)[0]
        d = payload[2:]
        name = KIND_NAMES.get(code)
        if code == PRESSURE_SET or code == AUTO_START_PRESSURE:
            events.append(Event(name, t, value=d[0]))
        elif code == BILEVEL_PRESSURE_SET:
            events.append(Event(name, t, value=d[0], value2=d[1]))
        elif code == PRESSURE_PULSE:
            events.append(Event(name, t, value=d[0]))
        elif code in (
            RERA,
            OBSTRUCTIVE_APNEA,
            CLEAR_AIRWAY_APNEA,
            FLOW_LIMITATION,
            HYPOPNEA_A,
            HYPOPNEA,
            HYPOPNEA_C,
        ):
            events.append(Event(name, t - d[0]))
        elif code == HYPOPNEA_B:
            events.append(Event(name, t - d[1], value=d[0]))
        elif code == VIBRATORY_SNORE:
            events.append(Event(name, t))
        elif code in (VARIABLE_BREATHING, PERIODIC_BREATHING, LARGE_LEAK):
            span = 2 * struct.unpack_from("<H", d)[0]
            since = d[2]
            events.append(Event(name, t - since - span, duration=span))
        elif code == INTERVAL_STATISTICS:
            intervals.append(IntervalStatistics(t, d[0], d[1], d[2]))
    return Events(
        session=sid,
        timestamp=chunk.timestamp,
        duration=t,
        events=events,
        intervals=intervals,
        snores_at_pressure=snores,
    )
