"""Command line: look at a card, list its sessions, export them, or dump one file's records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .card import read_card
from .chunk import parse_chunks, records
from .errors import FormatError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dreamstation", description=__doc__)
    ap.add_argument("--version", action="version", version=f"dreamstation {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("info", help="the device and a count of sessions")
    p.add_argument("card", type=Path)

    p = sub.add_parser("sessions", help="one line per session")
    p.add_argument("card", type=Path)

    p = sub.add_parser("export", help="every session as JSON, one object per line or one array")
    p.add_argument("card", type=Path)
    p.add_argument("--array", action="store_true", help="one JSON array instead of JSON lines")

    p = sub.add_parser("dump", help="the raw records of one .001 or .002 file, for format work")
    p.add_argument("file", type=Path)

    args = ap.parse_args(argv)
    try:
        return _run(args)
    except FormatError as e:
        print(f"dreamstation: {e}", file=sys.stderr)
        return 2


def _run(args) -> int:
    if args.command == "dump":
        for chunk in parse_chunks(args.file.read_bytes(), str(args.file)):
            sizes = dict(sorted(chunk.sizes.items()))
            print(
                f"chunk @{chunk.offset} kind={chunk.kind} "
                f"family={chunk.family}.{chunk.family_version} "
                f"session={chunk.session:#x} timestamp={chunk.timestamp} sizes={sizes}"
            )
            for code, payload in records(chunk):
                print(f"  {code:#04x} {payload.hex(' ')}")
        return 0

    card = read_card(args.card)
    if args.command == "info":
        d = card.device
        print(f"device   {d.model} serial {d.serial} software {d.software_version}")
        print(f"family   {d.family} version {d.family_version}")
        print(f"sessions {len(card.sessions)}")
        if card.sessions:
            print(f"first    {card.sessions[0].start.isoformat()}")
            print(f"last     {card.sessions[-1].end.isoformat()}")
        if card.skipped_files:
            print(f"events without a summary: {len(card.skipped_files)}")
        return 0
    if args.command == "sessions":
        print("session   start (UTC)          hours  mask-on   AHI  OA  CA   H  leak95")
        for s in card.sessions:
            st = s.summary.statistics
            leak = s.leak()
            print(
                f"{s.number:08x}  {s.start.strftime('%Y-%m-%d %H:%M:%S')}  "
                f"{s.duration_seconds / 3600:5.2f}  {s.mask_on_hours:7.2f}  "
                f"{_fmt(s.ahi):>4}  {st.obstructive_apneas if st else '-':>2}  "
                f"{st.clear_airway_apneas if st else '-':>2}  {st.hypopneas if st else '-':>2}  "
                f"{leak.percentile_95 if leak else '-':>6}"
            )
        return 0
    if args.command == "export":
        rows = [s.to_dict() for s in card.sessions]
        if args.array:
            json.dump(rows, sys.stdout, indent=1)
            print()
        else:
            for r in rows:
                print(json.dumps(r, separators=(",", ":")))
        return 0
    return 1


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.1f}"


if __name__ == "__main__":
    sys.exit(main())
