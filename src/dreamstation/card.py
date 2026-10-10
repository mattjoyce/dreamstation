"""Read a whole SD card: the device properties and every session.

Chunks are grouped by the session number in their headers, not by file name, because a file may
hold several sessions' chunks when the card was out of the device overnight. A byte-identical
chunk seen twice is counted as a duplicate and ignored; two different chunks claiming the same
session and kind are an error, since this library has no basis to choose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .chunk import EVENTS, SUMMARY, Chunk, parse_chunks
from .errors import FormatError, UnsupportedDeviceError
from .events import parse_events
from .session import Session
from .summary import parse_summary

SESSION_SUFFIXES = {".001": SUMMARY, ".002": EVENTS}


@dataclass
class Device:
    """What PROP.TXT says about the device that wrote the card."""

    serial: str
    model: str
    software_version: str
    family: int
    family_version: int
    properties: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_prop(cls, text: str) -> Device:
        props: dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if "=" in line:
                k, _, v = line.partition("=")
                props[k.strip()] = v.strip()
        try:
            return cls(
                serial=props["SN"],
                model=props["MN"],
                software_version=props.get("SV", ""),
                family=int(props["F"]),
                family_version=int(props["FV"]),
                properties=props,
            )
        except KeyError as e:
            raise FormatError(f"PROP.TXT lacks {e.args[0]}") from None


@dataclass
class Card:
    """A card: its device and its sessions in start order."""

    root: Path
    device: Device
    sessions: list[Session]
    skipped_files: list[str] = field(default_factory=list)

    def session(self, number: int) -> Session | None:
        for s in self.sessions:
            if s.number == number:
                return s
        return None


def find_device_dir(path: Path) -> Path:
    """Given the card root, the P-SERIES folder or the serial folder, return the serial folder."""
    path = Path(path)
    if (path / "PROP.TXT").exists():
        return path
    for candidate in (path, path / "P-SERIES"):
        if candidate.is_dir():
            dirs = [d for d in candidate.iterdir() if d.is_dir() and (d / "PROP.TXT").exists()]
            if len(dirs) == 1:
                return dirs[0]
            if len(dirs) > 1:
                raise FormatError(f"{candidate} holds {len(dirs)} devices; name one")
    raise FormatError(f"{path} is not a DreamStation card (no PROP.TXT found)")


def session_files(device_dir: Path) -> list[Path]:
    """Every summary and events file under the P folders, in folder and name order."""
    out: list[Path] = []
    for folder in sorted(p for p in device_dir.iterdir() if p.is_dir() and _is_p_folder(p.name)):
        for f in sorted(folder.iterdir()):
            if f.suffix in SESSION_SUFFIXES and f.is_file():
                out.append(f)
    return out


def _is_p_folder(name: str) -> bool:
    return len(name) >= 2 and name[0] == "P" and name[1:].isdigit()


def read_card(path: str | Path) -> Card:
    """Read every session on the card.

    Raises FormatError on anything the format note does not cover.
    """
    device_dir = find_device_dir(Path(path))
    device = Device.from_prop((device_dir / "PROP.TXT").read_text(errors="replace"))
    if (device.family, device.family_version) != (0, 6):
        raise UnsupportedDeviceError(
            f"{device.model} is family {device.family} version {device.family_version}; "
            "only DreamStation (family 0, version 6) is read",
            path=str(device_dir / "PROP.TXT"),
        )
    summaries: dict[int, Chunk] = {}
    events: dict[int, Chunk] = {}
    duplicates: dict[int, int] = {}
    for f in session_files(device_dir):
        for chunk in parse_chunks(f.read_bytes(), str(f)):
            if chunk.kind not in (SUMMARY, EVENTS):
                raise FormatError(
                    f"chunk kind {chunk.kind} in a session file", path=str(f), session=chunk.session
                )
            table = summaries if chunk.kind == SUMMARY else events
            prior = table.get(chunk.session)
            if prior is None:
                table[chunk.session] = chunk
            elif prior.data == chunk.data and prior.timestamp == chunk.timestamp:
                duplicates[chunk.session] = duplicates.get(chunk.session, 0) + 1
            else:
                raise FormatError(
                    f"two different {('summary', 'events')[chunk.kind - 1]} chunks for one session "
                    f"({prior.path} and {f})",
                    path=str(f),
                    session=chunk.session,
                )
    sessions: list[Session] = []
    for number, chunk in summaries.items():
        summary = parse_summary(chunk)
        ev = events.pop(number, None)
        parsed_events = parse_events(ev) if ev is not None else None
        if parsed_events is not None and parsed_events.timestamp != summary.timestamp:
            raise FormatError(
                "events and summary disagree on the session start", path=chunk.path, session=number
            )
        sessions.append(Session(summary, parsed_events, duplicates.get(number, 0)))
    orphans = [f"{c.path} (session {n:#x})" for n, c in events.items()]
    sessions.sort(key=lambda s: (s.summary.timestamp, s.number))
    return Card(root=device_dir, device=device, sessions=sessions, skipped_files=orphans)
