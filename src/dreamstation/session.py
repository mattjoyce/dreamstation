"""A therapy session: the summary and events for one session number, with derived figures.

The device's own counts (from the summary's statistics record) and the counts this library
takes from the events file are kept apart. On the card this was written against they agree
exactly for every count and nearly so for the minute totals; keeping both lets a reader see
when they do not.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .events import Events
from .summary import Summary


@dataclass(frozen=True)
class LeakStatistics:
    """Total leak over the session's two-minute intervals, litres per minute."""

    mean: float
    percentile_95: int
    maximum: int
    intervals: int


@dataclass
class Session:
    """One session, assembled from its summary and, when present, its events."""

    summary: Summary
    events: Events | None = None
    duplicates: int = field(default=0)  # byte-identical chunks seen more than once

    @property
    def number(self) -> int:
        return self.summary.session

    @property
    def start(self) -> datetime:
        return datetime.fromtimestamp(self.summary.timestamp, tz=UTC)

    @property
    def end(self) -> datetime:
        return self.start + timedelta(seconds=self.summary.duration)

    @property
    def duration_seconds(self) -> int:
        return self.summary.duration

    @property
    def mask_on_seconds(self) -> int:
        return sum(s.seconds for s in self.summary.slices)

    @property
    def mask_on_hours(self) -> float:
        return self.mask_on_seconds / 3600

    def event_counts(self) -> Counter[str]:
        """Counts of each event kind from the events file, empty without one."""
        if self.events is None:
            return Counter()
        return Counter(e.kind for e in self.events.events)

    def span_seconds(self) -> Counter[str]:
        """Total seconds of each span kind (large leak, periodic and variable breathing)."""
        c: Counter[str] = Counter()
        if self.events is None:
            return c
        for e in self.events.events:
            if e.duration:
                c[e.kind] += e.duration
        return c

    def index(self, count: int) -> float | None:
        """``count`` per hour of mask-on time, or None when the mask was never on."""
        hours = self.mask_on_hours
        return count / hours if hours > 0 else None

    @property
    def ahi(self) -> float | None:
        """Apnoea-hypopnoea index from the device's own counts, per hour of mask-on time."""
        s = self.summary.statistics
        if s is None:
            return None
        return self.index(s.obstructive_apneas + s.clear_airway_apneas + s.hypopneas)

    @property
    def rdi(self) -> float | None:
        """Respiratory disturbance index: AHI plus RERAs, per hour of mask-on time."""
        s = self.summary.statistics
        if s is None:
            return None
        return self.index(s.obstructive_apneas + s.clear_airway_apneas + s.hypopneas + s.reras)

    def leak(self) -> LeakStatistics | None:
        if self.events is None or not self.events.intervals:
            return None
        leaks = sorted(i.total_leak for i in self.events.intervals)
        n = len(leaks)
        return LeakStatistics(
            mean=sum(leaks) / n,
            percentile_95=leaks[min(n - 1, int(0.95 * n))],
            maximum=leaks[-1],
            intervals=n,
        )

    def to_dict(self) -> dict:
        """A plain, JSON-ready view of the session: times, settings, device statistics, indexes."""
        st = self.summary.statistics
        p = self.summary.pressure
        settings = self.summary.settings
        d: dict = {
            "session": self.number,
            "session_hex": f"{self.number:08X}",
            "start": self.start.isoformat().replace("+00:00", "Z"),
            "end": self.end.isoformat().replace("+00:00", "Z"),
            "duration_seconds": self.duration_seconds,
            "mask_on_seconds": self.mask_on_seconds,
            "mask_on_spans": [[s.start, s.end] for s in self.summary.slices],
            "settings": _settings_dict(settings),
        }
        if p is not None:
            d["pressure"] = {
                "minimum": p.minimum / 10,
                "maximum": p.maximum / 10,
                "percentile_90": p.percentile_90 / 10,
                "mean": p.mean / 10,
            }
        if st is not None:
            d["device_counts"] = {
                "obstructive_apneas": st.obstructive_apneas,
                "clear_airway_apneas": st.clear_airway_apneas,
                "hypopneas": st.hypopneas,
                "reras": st.reras,
                "flow_limitations": st.flow_limitations,
                "snores": st.snores,
                "large_leak_minutes": st.large_leak_minutes,
                "periodic_breathing_minutes": st.periodic_breathing_minutes,
                "variable_breathing_minutes": st.variable_breathing_minutes,
            }
            d["ahi"] = _round(self.ahi)
            d["rdi"] = _round(self.rdi)
        if self.events is not None:
            counts = self.event_counts()
            spans = self.span_seconds()
            d["event_counts"] = dict(sorted(counts.items()))
            d["span_seconds"] = dict(sorted(spans.items()))
            leak = self.leak()
            if leak is not None:
                d["leak"] = {
                    "mean": round(leak.mean, 1),
                    "percentile_95": leak.percentile_95,
                    "maximum": leak.maximum,
                    "intervals": leak.intervals,
                }
        if self.duplicates:
            d["duplicate_chunks"] = self.duplicates
        return d


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, 2)


def _settings_dict(s) -> dict:
    out: dict = {"mode": s.mode}
    for name in (
        "pressure",
        "pressure_min",
        "pressure_max",
        "epap",
        "ipap",
        "epap_min",
        "ipap_max",
        "pressure_support_min",
        "pressure_support_max",
        "ramp_pressure",
    ):
        v = getattr(s, name)
        if v is not None:
            out[name] = v / 10
    for name in (
        "auto_trial_days",
        "ramp_type",
        "ramp_minutes",
        "flex_mode",
        "flex_level",
        "humidifier_target_hours",
        "tubing_mm",
        "tubing_heated",
        "mask_resistance",
    ):
        v = getattr(s, name)
        if v is not None:
            out[name] = v
    if s.humidifier is not None:
        h = s.humidifier
        out["humidifier"] = {
            "mode": h.mode,
            "level": h.level,
            "tube_temperature": h.tube_temperature,
        }
    if s.comfort_flags is not None:
        out["comfort_flags"] = s.comfort_flags
    out.update(s.flags)
    return out
