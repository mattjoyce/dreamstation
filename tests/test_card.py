"""Reading a whole card from a synthetic directory, and the real card when one is named."""

import json
import os
from pathlib import Path

import pytest
from build import SESSION_START, ev, events_file, statistics_record, summary_data, summary_file

from dreamstation import read_card
from dreamstation.cli import main
from dreamstation.errors import FormatError, UnsupportedDeviceError

PROP = "CF=4\nSN=TEST0001\nMN=500X150\nSV=V1.1.8.3313\nF=0\nFV=6\nDF=0\nDFV=3\nFN=0\n"


def make_card(tmp_path: Path, prop: str = PROP) -> Path:
    dev = tmp_path / "P-SERIES" / "12345678"
    (dev / "P0").mkdir(parents=True)
    (dev / "PROP.TXT").write_text(prop)
    (tmp_path / "P-SERIES" / "LAST.TXT").write_text("12345678\n")
    return dev


def write_session(dev: Path, number: int, timestamp: int, *, oa=0, hy=0, folder="P0", events=True):
    stats = statistics_record(oa=oa, hy=hy)
    data = summary_data(mask_off_after=3600, stats=stats)
    (dev / folder).mkdir(exist_ok=True)
    (dev / folder / f"{number:08X}.001").write_bytes(summary_file(number, timestamp, data))
    if events:
        evdata = b"".join(ev(0x06, 100, 5) for _ in range(oa)) + b"".join(
            ev(0x14, 100, 10) for _ in range(hy)
        )
        evdata += ev(0x11, 120, 30, 0, 100)
        (dev / folder / f"{number:08X}.002").write_bytes(events_file(number, timestamp, evdata))


def test_reads_sessions_in_time_order_across_folders(tmp_path):
    dev = make_card(tmp_path)
    write_session(dev, 0x12, SESSION_START + 86400, oa=2, hy=1, folder="P1")
    write_session(dev, 0x11, SESSION_START, oa=1)
    card = read_card(tmp_path)  # the card root, not the serial folder
    assert card.device.serial == "TEST0001" and card.device.model == "500X150"
    assert [s.number for s in card.sessions] == [0x11, 0x12]
    s = card.sessions[1]
    assert s.start.isoformat() == "2023-11-15T22:13:20+00:00"
    assert s.mask_on_seconds == 3600
    assert s.summary.statistics.obstructive_apneas == 2
    assert s.event_counts()["obstructive_apnea"] == 2
    assert s.ahi == pytest.approx(3.0)
    assert s.rdi == pytest.approx(3.0)
    assert s.leak().mean == 30


def test_accepts_the_serial_folder_and_the_p_series_folder(tmp_path):
    dev = make_card(tmp_path)
    write_session(dev, 1, SESSION_START)
    assert len(read_card(dev).sessions) == 1
    assert len(read_card(tmp_path / "P-SERIES").sessions) == 1


def test_session_without_events(tmp_path):
    dev = make_card(tmp_path)
    write_session(dev, 1, SESSION_START, events=False)
    (s,) = read_card(dev).sessions
    assert s.events is None and s.event_counts() == {} and s.leak() is None
    assert "event_counts" not in s.to_dict()


def test_identical_duplicate_chunk_is_counted_not_doubled(tmp_path):
    dev = make_card(tmp_path)
    write_session(dev, 1, SESSION_START)
    (dev / "P1").mkdir()
    (dev / "P1" / "00000001.001").write_bytes((dev / "P0" / "00000001.001").read_bytes())
    (s,) = read_card(dev).sessions
    assert s.duplicates == 1


def test_conflicting_chunks_for_one_session_are_refused(tmp_path):
    dev = make_card(tmp_path)
    write_session(dev, 1, SESSION_START)
    (dev / "P1").mkdir()
    (dev / "P1" / "00000001.001").write_bytes(summary_file(1, SESSION_START + 5))
    with pytest.raises(FormatError, match="two different summary chunks"):
        read_card(dev)


def test_events_start_must_match_summary(tmp_path):
    dev = make_card(tmp_path)
    write_session(dev, 1, SESSION_START, events=False)
    (dev / "P0" / "00000001.002").write_bytes(events_file(1, SESSION_START + 1))
    with pytest.raises(FormatError, match="disagree on the session start"):
        read_card(dev)


def test_other_family_in_prop_is_refused(tmp_path):
    dev = make_card(tmp_path, PROP.replace("FV=6", "FV=4"))
    with pytest.raises(UnsupportedDeviceError, match="family 0 version 4"):
        read_card(dev)


def test_not_a_card(tmp_path):
    with pytest.raises(FormatError, match="no PROP.TXT"):
        read_card(tmp_path)


def test_cli_export_and_info(tmp_path, capsys):
    dev = make_card(tmp_path)
    write_session(dev, 7, SESSION_START, oa=1)
    assert main(["export", str(tmp_path)]) == 0
    (line,) = capsys.readouterr().out.strip().splitlines()
    row = json.loads(line)
    assert row["session"] == 7 and row["session_hex"] == "00000007"
    assert row["ahi"] == 1.0 and row["settings"]["mode"] == "auto_cpap"
    assert main(["info", str(tmp_path)]) == 0
    assert "sessions 1" in capsys.readouterr().out


def test_cli_reports_format_errors(tmp_path, capsys):
    assert main(["info", str(tmp_path)]) == 2
    assert "no PROP.TXT" in capsys.readouterr().err


REAL = os.environ.get("DREAMSTATION_CARD")


@pytest.mark.skipif(not REAL, reason="set DREAMSTATION_CARD to a card to run")
def test_real_card_is_self_consistent():
    """Every session parses, and the device's counts equal the events file's counts."""
    card = read_card(REAL)
    assert card.sessions
    for s in card.sessions:
        assert s.duration_seconds >= s.mask_on_seconds >= 0
        if s.events is None:
            continue
        assert s.events.duration <= s.duration_seconds + 1
        st, counts = s.summary.statistics, s.event_counts()
        assert st.obstructive_apneas == counts["obstructive_apnea"], s.number
        assert st.clear_airway_apneas == counts["clear_airway_apnea"], s.number
        assert st.hypopneas == counts["hypopnea"], s.number
        assert st.reras == counts["rera"], s.number
        assert st.flow_limitations == counts["flow_limitation"], s.number
        assert st.snores == sum(x.snores for x in s.events.snores_at_pressure), s.number
