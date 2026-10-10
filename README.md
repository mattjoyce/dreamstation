# dreamstation

Read therapy data from a Philips DreamStation CPAP SD card: sessions, settings, respiratory
events, pressure and leak statistics. Pure Python, no dependencies, no vendor software.

```
$ dreamstation info /media/sd/P-SERIES
device   500X150 serial J1234567890AB software V1.1.8.3313
family   0 version 6
sessions 412
first    2025-01-03T11:02:40+00:00
last     2026-03-14T12:47:09+00:00

$ dreamstation sessions /media/sd/P-SERIES | tail -3
session   start (UTC)          hours  mask-on   AHI  OA  CA   H  leak95
0000019A  2026-03-12 12:31:05   6.10     6.10   1.0   2   1   3      38
0000019B  2026-03-13 12:15:52   0.42     0.42   0.0   0   0   0      30
0000019C  2026-03-14 12:47:09   5.80     5.80   0.7   1   0   3      36

$ dreamstation export /media/sd/P-SERIES > sessions.jsonl
```

```python
from dreamstation import read_card

card = read_card("/media/sd/P-SERIES")
for s in card.sessions:
    print(s.start, round(s.mask_on_hours, 2), s.ahi, s.summary.settings.pressure_max / 10)
```

## What you get

For each session the device recorded:

- start and end as UTC instants, duration, and the mask-on spans within it;
- the settings in force: therapy mode, pressure range, ramp, pressure relief, humidifier,
  tubing, and the lock and comfort flags;
- the device's own session summary: minimum, maximum, 90th percentile and mean pressure, and its
  counts of obstructive apnoeas, clear-airway apnoeas, hypopnoeas, RERAs, flow limitations and
  snores, with minutes of large leak, periodic breathing and variable breathing;
- every event from the events file with its time, and the two-minute leak, snore and pressure
  statistics;
- AHI and RDI per hour of mask-on time, and leak mean, 95th percentile and maximum.

The device's counts and the counts taken from the events file are reported side by side. On the
card this was written against they agree exactly for every count in every one of 1,317 sessions.

Nothing is read from the flow waveform files.

## Supported devices

DreamStation CPAP and Auto CPAP machines whose card reports data family 0, version 6 (the
`F=0` and `FV=6` lines of `PROP.TXT`). The library stops with a clear error on any other family,
any file format version other than 3, and any record code, setting code or event code that
[the format note](docs/FORMAT.md) does not describe. That is deliberate: an unknown code needs
a decision, not a guess, and a guess in health data is worse than a stop. If it stops on your
card, the `dump` command prints the raw records so the code can be identified and added.

Tested on one Auto CPAP (500X150, firmware 1.1.8). Bi-level, CPAP-Check and DreamStation Go
settings are decoded from the format note but have not been seen on a real card by this library.

## Installation

```
pip install dreamstation
```

or from a checkout, `uv sync` and `uv run dreamstation --help`.

## Times

The device stamps each session with a true UTC instant, so times are correct whatever time zone
you were in. Nothing on the card records the zone, so grouping sessions into nights is up to the
reader. The usual rule, which OSCAR uses, is that a night runs from noon to noon local time.

## How the format was established

From the bytes on one card, checked against every one of its 1,317 sessions, and from reading
the loader in the [OSCAR](https://www.sleepfiles.com/OSCAR/) project to learn what the fields
mean. OSCAR is GPL-licensed software; nothing from it is copied here, and this library is not
derived from it. Where this library's understanding came from OSCAR's, the format note says so.
The statistics record in the summary file, which OSCAR leaves undecoded, was identified here by
matching its words against the events file across the whole card.

[docs/FORMAT.md](docs/FORMAT.md) is the full account, including what is still unknown.

## Not medical advice

This reads what the machine wrote. It does not interpret it. Talk to your sleep physician about
what the numbers mean for you.

## Licence

Apache License 2.0. See [LICENSE](LICENSE).
