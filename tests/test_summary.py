"""The summary file: time records, settings, pressure summary, statistics, and refusals."""

import struct

import pytest
from build import (
    SUMMARY_SIZES,
    chunk,
    settings_record,
    statistics_record,
    summary_data,
    summary_file,
)

from dreamstation.chunk import parse_chunks
from dreamstation.errors import FormatError, UnsupportedDeviceError
from dreamstation.summary import parse_summary


def _summary(data=None, **kw):
    (c,) = parse_chunks(summary_file(data=data, **kw), "P0/00000010.001")
    return parse_summary(c)


def test_times_accumulate_from_each_record():
    s = _summary(summary_data(mask_on_at=30, mask_off_after=7200, off_after=15))
    assert s.duration == 30 + 7200 + 15
    assert [(sl.start, sl.end) for sl in s.slices] == [(30, 7230)]
    assert s.slices[0].seconds == 7200


def test_two_mask_on_spans():
    settings, stats = settings_record(), statistics_record()
    data = (
        bytes((0, 1, 1)) + settings
        + bytes((3,)) + struct.pack("<H", 0) + b"\x8c\x6c"
        + bytes((4,)) + struct.pack("<H", 100)
        + bytes((3,)) + struct.pack("<H", 50) + b"\x8c\x6c"
        + bytes((5,)) + bytes((100, 120, 110, 105))
        + bytes((4,)) + struct.pack("<H", 200)
        + bytes((8,)) + stats
        + bytes((2,)) + struct.pack("<H", 0) + bytes(7)
    )  # fmt: skip
    s = _summary(data)
    assert [(sl.start, sl.end) for sl in s.slices] == [(0, 100), (150, 350)]
    assert s.duration == 350


def test_mask_still_on_at_equipment_off_closes_the_span():
    data = (
        bytes((0, 1, 1)) + settings_record()
        + bytes((3,)) + struct.pack("<H", 0) + b"\x8c\x6c"
        + bytes((2,)) + struct.pack("<H", 500) + bytes(7)
    )  # fmt: skip
    s = _summary(data)
    assert [(sl.start, sl.end) for sl in s.slices] == [(0, 500)]


def test_pressure_summary_and_statistics_words():
    stats = statistics_record(
        oa=4, ca=1, hy=7, rera=6, fl=2, snores=9, ll_min=3, pb_min=2, vb_min=68
    )
    s = _summary(summary_data(pressure=(100, 125, 110, 103), stats=stats))
    assert (s.pressure.minimum, s.pressure.maximum, s.pressure.percentile_90, s.pressure.mean) == (
        100,
        125,
        110,
        103,
    )
    st = s.statistics
    assert (st.obstructive_apneas, st.clear_airway_apneas, st.hypopneas) == (4, 1, 7)
    assert (st.reras, st.flow_limitations, st.snores) == (6, 2, 9)
    assert (
        st.large_leak_minutes,
        st.periodic_breathing_minutes,
        st.variable_breathing_minutes,
    ) == (
        3,
        2,
        68,
    )
    assert st.unknown_words == (0, 0, 0, 10000, 70, 0x0E00, 50)


def test_settings_are_decoded():
    s = _summary(
        summary_data(settings=settings_record(pressure_min=90, pressure_max=140, tubing=2))
    )
    st = s.settings
    assert st.mode == "auto_cpap"
    assert (st.pressure_min, st.pressure_max, st.ramp_pressure) == (90, 140, 90)
    assert (st.ramp_type, st.ramp_minutes) == ("smart", 5)
    assert (st.flex_mode, st.flex_level) == ("c_flex", 3)
    assert st.humidifier.mode == "none" and not st.humidifier.present
    assert (st.tubing_mm, st.tubing_heated) == (15, True)
    assert st.flags["auto_on"] is True and st.flags["show_ahi"] is False


def test_heated_tube_humidifier_bytes():
    s = _summary(summary_data(settings=settings_record(humidifier=(0x4C, 0x6C))))
    h = s.settings.humidifier
    assert (h.mode, h.level, h.tube_temperature, h.present) == ("heated_tube", 3, 3, True)


def test_mask_on_carries_humidifier_status():
    s = _summary(summary_data(humidifier=(0x4C, 0x6C)))
    assert s.slices[0].humidifier.mode == "heated_tube"


def test_unknown_summary_code_is_refused():
    data = summary_data() + bytes((12, 0))  # code 0x0c has a size but no meaning here
    with pytest.raises(FormatError, match="0x0c is not known"):
        _summary(data)


def test_unknown_setting_code_is_refused():
    data = summary_data(settings=settings_record(extra=bytes((0x50, 1, 0))))
    with pytest.raises(FormatError, match="setting code 0x50"):
        _summary(data)


def test_unknown_therapy_mode_is_refused():
    with pytest.raises(FormatError, match="therapy mode 9"):
        _summary(summary_data(settings=settings_record(mode=9)))


def test_other_family_is_refused():
    # Patch the family version and repair the header checksum that covers it.
    raw = bytearray(chunk(1, 0x10, 0, SUMMARY_SIZES, summary_data()))
    raw[5] = 4
    raw[16 + 2 * len(SUMMARY_SIZES)] = (raw[16 + 2 * len(SUMMARY_SIZES)] + 4 - 6) & 0xFF
    (c,) = parse_chunks(bytes(raw))
    with pytest.raises(UnsupportedDeviceError, match="family 0 version 4"):
        parse_summary(c)


def test_events_chunk_is_not_a_summary():
    from build import events_file

    (c,) = parse_chunks(events_file())
    with pytest.raises(FormatError, match="not a summary"):
        parse_summary(c)
