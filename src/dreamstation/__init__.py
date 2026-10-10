"""Read therapy data from a Philips DreamStation CPAP SD card.

    from dreamstation import read_card
    card = read_card("/media/sd/P-SERIES")
    for s in card.sessions:
        print(s.start, s.mask_on_hours, s.ahi)

See docs/FORMAT.md for what the files hold and how it was established.
"""

from .card import Card, Device, read_card
from .chunk import Chunk, parse_chunks
from .errors import FormatError, UnsupportedDeviceError
from .events import Event, Events, IntervalStatistics, SnoresAtPressure, parse_events
from .session import LeakStatistics, Session
from .settings import Humidifier, Settings
from .summary import PressureSummary, Slice, Statistics, Summary, parse_summary

__version__ = "0.1.0"

__all__ = [
    "Card",
    "Chunk",
    "Device",
    "Event",
    "Events",
    "FormatError",
    "Humidifier",
    "IntervalStatistics",
    "LeakStatistics",
    "PressureSummary",
    "Session",
    "Settings",
    "Slice",
    "SnoresAtPressure",
    "Statistics",
    "Summary",
    "UnsupportedDeviceError",
    "parse_chunks",
    "parse_events",
    "parse_summary",
    "read_card",
]
