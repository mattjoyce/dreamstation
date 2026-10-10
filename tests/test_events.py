"""The events file: time accumulation, event placement, spans, statistics and refusals."""

import pytest
from build import ev, events_file

from dreamstation.chunk import parse_chunks
from dreamstation.errors import FormatError
from dreamstation.events import parse_events


def _events(data: bytes):
    (c,) = parse_chunks(events_file(data=data), "P0/00000010.002")
    return parse_events(c)


def test_point_events_are_placed_by_elapsed_delay():
    data = (
        ev(0x01, 0, 100) + ev(0x06, 600, 12) + ev(0x07, 60, 5) + ev(0x14, 30, 20) + ev(0x05, 10, 3)
    )
    e = _events(data)
    kinds = [(x.kind, x.time) for x in e.events]
    assert kinds == [
        ("pressure_set", 0),
        ("obstructive_apnea", 588),
        ("clear_airway_apnea", 655),
        ("hypopnea", 670),
        ("rera", 697),
    ]
    assert e.duration == 700


def test_spans_carry_two_second_units_and_end_before_the_report():
    # Reported at t=1000, lasted 2*30 = 60 s, ended 20 s before the report.
    e = _events(ev(0x10, 1000, 30, 0, 20))
    (ll,) = e.events
    assert (ll.kind, ll.time, ll.duration) == ("large_leak", 920, 60)


def test_hypopnea_variant_b_keeps_its_unknown_byte():
    e = _events(ev(0x0B, 100, 7, 15))
    (h,) = e.events
    assert (h.kind, h.time, h.value) == ("hypopnea_variant_b", 85, 7)


def test_pressure_events():
    e = _events(ev(0x01, 0, 100) + ev(0x02, 10, 80, 120) + ev(0x03, 5, 100) + ev(0x04, 1, 9))
    assert [(x.kind, x.value, x.value2) for x in e.events] == [
        ("pressure_set", 100, None),
        ("bilevel_pressure_set", 80, 120),
        ("auto_start_pressure", 100, None),
        ("pressure_pulse", 9, None),
    ]


def test_interval_statistics_and_snores_at_pressure():
    data = ev(0x11, 120, 33, 2, 101) + ev(0x11, 120, 35, 0, 102) + bytes((0x12, 0, 100, 2, 0))
    e = _events(data)
    assert [(i.time, i.total_leak, i.snores, i.pressure) for i in e.intervals] == [
        (120, 33, 2, 101),
        (240, 35, 0, 102),
    ]
    (s,) = e.snores_at_pressure
    assert (s.pressure_kind, s.pressure, s.snores) == ("cpap", 100, 2)
    assert e.duration == 240  # the snore record carries no time


def test_vibratory_snore_has_no_data():
    e = _events(ev(0x0D, 42))
    assert [(x.kind, x.time) for x in e.events] == [("vibratory_snore", 42)]


def test_empty_events_file():
    e = _events(b"")
    assert e.events == [] and e.intervals == [] and e.duration == 0


def test_unknown_event_code_is_refused():
    with pytest.raises(FormatError, match="event code 0x13"):
        _events(bytes((0x13, 0, 0, 0)))


def test_unknown_snore_pressure_kind_is_refused():
    with pytest.raises(FormatError, match="snore pressure kind 7"):
        _events(bytes((0x12, 7, 100, 0, 0)))
