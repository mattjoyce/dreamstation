# DreamStation SD card format, as observed

This note describes the files a Philips DreamStation CPAP writes to its SD card, as far as this
library reads them. It is written from the bytes on one card (a DreamStation Auto CPAP, model
500X150, firmware 1.1.8, about 1,300 sessions) and from reading
the OSCAR project's loader to learn what the fields mean. OSCAR is GPL software and nothing of it
is copied here; it is cited as the source of the understanding where that is what it is.

Philips calls the family "PRS1" (Philips Respironics System One) and the DreamStation data format
"family 0, version 6". Other families and versions share the chunk container below but differ in
every payload, and this library refuses them rather than guess.

Numbers are little-endian unless stated. Pressures are in tenths of a centimetre of water
(a byte of 100 is 10.0 cm H2O). Times inside a session are seconds since the session start.

## Card layout

```
P-SERIES/
  LAST.TXT               the serial number of the last device to write the card
  <serial>/
    PROP.TXT             device properties, key=value, one per line
    LOG.SEQ              unknown, small
    P0/ P1/ ... Pn/      session files, up to about 500 files per folder
      <session>.001      summary (settings, mask on and off times, statistics), 100 to 200 bytes
      <session>.002      events, a few kilobytes
      <session>.005      flow waveform, tens to hundreds of kilobytes, not read here
    D/ E/                small, unknown, not read
```

Session file names are the session number in hexadecimal, eight digits. The device starts a new
folder when the current one is full and may split a long session's waveform across folders.

Keys seen in `PROP.TXT` (meaning as observed; unlabelled ones are unknown):

| Key | Seen | Meaning |
|---|---|---|
| SN | J1234567890AB | serial number, redacted here |
| MN | 500X150 | model number |
| SV | V1.1.8.3313 | software version |
| F, FV | 0, 6 | data family and family version |
| DF, DFV | 0, 3 | data file format and its version (3 is the chunk version below) |
| FD, LD | 1712365200, 1791507600 | first and last session dates, as epoch seconds at local midnight |
| FN | 7 | number of the current P folder |
| PFN, EFN, DFN | 453, 1, 2 | file counts in the P, E and D folders |
| CF, PT, SID, TS, DC, BK, SK, EK, DK, VC, P, G, DPK | | unknown |

## The chunk container

Every `.001` and `.002` file holds one or more chunks back to back. A chunk is a header, an
8-bit header checksum, a data block, and a 32-bit CRC.

Fixed header, 15 bytes:

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | file format version; 3 on every DreamStation file, 2 on older devices |
| 1 | 2 | block size, the whole chunk including this header and the trailing CRC |
| 3 | 1 | header type; 0 for the summary and events files, 1 for waveform files |
| 4 | 1 | family; 0 |
| 5 | 1 | family version; 6 |
| 6 | 1 | file kind, the same number as the file extension: 1 summary, 2 events, 5 waveform |
| 7 | 4 | session number |
| 11 | 4 | session start, Unix epoch seconds, UTC |

The session start is a true UTC instant. On the card surveyed, starts cluster between 22:00 and
midnight Sydney time when read as UTC, and the FAT modification time of a session's files (which
the device writes as local wall-clock time) is one second after the session's start plus its
duration. Nothing in the file says which time zone the person was in.

For header type 0 and format version 3, byte 15 is a count N, followed by N pairs of bytes: a
code and the size of that code's record in the data block. This is the **header block**. Record
sizes vary between devices and firmware, so a reader must take them from here and never assume.

After the header block comes one byte, the header checksum: the 8-bit sum of every header byte
before it.

The data block runs from there to four bytes before the end of the chunk. Those last four bytes
are a CRC-32 of the data block alone (not the header). The CRC is the MSB-first form with
polynomial 0x04C11DB7, initial value 0xFFFFFFFF and no final inversion, and it is fed each data
byte as a 32-bit word whose low byte is the data byte, that is, the byte sequence 0, 0, 0, b for
every b. This is the behaviour of a hardware CRC unit fed whole words, and OSCAR's loader is where
that was first worked out. Every chunk on the surveyed card verifies.

On the surveyed card every file holds exactly one chunk whose session number equals the file
name. OSCAR reports cards where a file holds several sessions' chunks, written when the card was
out of the device overnight, so a reader groups chunks by the session number in the header, not
by file name, and treats a repeated, byte-identical chunk as a duplicate.

## The summary file (.001)

The data block is a sequence of records: one code byte, then as many bytes as the header block
gives for that code. Codes seen, in the order the device writes them:

| Code | Size | Record |
|---|---|---|
| 0 | 1 | equipment on; one byte, always first |
| 1 | 54 | settings, a nested sequence described below |
| 3 | 4 | mask on: 16-bit seconds elapsed since the previous time record, then two humidifier status bytes |
| 5 | 4 | pressure summary: minimum, maximum, 90th percentile and mean pressure, one byte each |
| 4 | 2 | mask off: 16-bit seconds elapsed |
| 8 | 31 | statistics, described below |
| 2 | 9 | equipment off: 16-bit seconds elapsed, then seven bytes of unknown meaning |

Codes 6, 7, 9, 10 (0x0a), 11 (0x0b) and 12 (0x0c) have sizes in the header block but never
appear on this device. OSCAR documents some of them for other models (an elapsed-time record,
humidifier changes, CPAP-Check and EZ-Start pressures). A reader must stop on a code it does not
know, because the size is known but the meaning is not.

The time records (2, 3, 4) each carry the seconds since the previous time record. Summing them
in order gives each record's offset from the session start, and the equipment-off offset is the
session duration. A session may have several mask-on and mask-off pairs.

### Pressure summary (code 5)

Four pressure bytes. Against the pressure adjustments in the events file over 1,314 sessions:
the first equals the lowest pressure delivered in every session (and the minimum pressure
setting in all but one); the second is never below the highest adjustment seen and equals it in
88 per cent; the third and fourth are the device's own 90th percentile and mean, which an
estimate from the two-minute statistics only approximates. Treat these four as the device's
report of minimum, maximum, 90th percentile and mean pressure.

### Statistics (code 8)

Fifteen 16-bit words and one trailing byte. The identified words match a count or duration from
the same session's events file exactly, in every one of 1,314 sessions, unless stated:

| Word | Meaning | Verified against |
|---|---|---|
| 0 | unknown, 0 on this card | |
| 1 | obstructive apnoeas | event 0x06 count |
| 2 | unknown, 0 on this card | |
| 3 | clear-airway apnoeas | event 0x07 count |
| 4 | minutes of variable breathing, floored | event 0x0e durations; 93 per cent |
| 5 | minutes of large leak, floored | event 0x10 durations; 99.8 per cent |
| 6 | minutes of periodic breathing, floored | event 0x0f durations; 99.5 per cent |
| 7 | snore count | the per-interval snore counts summed |
| 8 | hypopnoeas | event 0x14 count; the device does not count the rarer 0x0b hypopnoea here |
| 9 | unknown, 0 on this card | |
| 10 | RERAs | event 0x05 count |
| 11 | flow limitations | event 0x0c count |
| 12 | unknown; 9,700 to 10,300 regardless of session length | |
| 13 | unknown; 61 to 82 | |
| 14 | unknown; low byte 0, high byte 12 to 17 | |
| byte 30 | unknown; 44 to 62 | |

The disagreements in words 4 to 6 are small and one-sided and look like the device timing the
spans to the second where the events file holds two-second units. The device's number is the
one its own reports show.

### Settings (code 1)

A nested sequence of code, length, value bytes. The codes and values seen on this device, an
Auto CPAP, and the meaning OSCAR's loader gives them:

| Code | Len | Meaning | Seen |
|---|---|---|---|
| 0x00 | 1 | therapy mode: 0 CPAP, 1 bi-level, 2 auto CPAP, 3 auto bi-level, 4 CPAP-Check | 2 |
| 0x01 | 1 or 2 | comfort flags; second byte 0x10 EZ-Start, 0x20 Opti-Start, 0x40 Auto-Trial, 0x80 CPAP-Check+ | 03 20 |
| 0x0a | 1 | CPAP pressure (CPAP mode) | |
| 0x0c | 3 | CPAP-Check minimum, maximum and pressure | |
| 0x0d | 2 | auto CPAP minimum and maximum pressure | |
| 0x0e | 2 | bi-level EPAP and IPAP | |
| 0x0f | 4 | auto bi-level EPAP minimum, IPAP maximum, pressure support minimum and maximum | |
| 0x10 | 3 | Auto-Trial days, minimum and maximum pressure | |
| 0x2a | 1 | EZ-Start, 0 or 0x80 | |
| 0x2b | 1 | ramp type: 0 linear, 0x80 SmartRamp | 0x80 |
| 0x2c | 1 | ramp time in minutes, 0 off | |
| 0x2d | 1 | ramp starting pressure | |
| 0x2e | 1 | pressure relief: 0 off, 0x80 C-Flex (Bi-Flex in bi-level), 0x90 C-Flex+ or A-Flex by mode, 0xa0 rise time, 0xb0 P-Flex | 0x80 |
| 0x2f | 1 | pressure relief locked, 0 or 0x80 | 0 |
| 0x30 | 1 | pressure relief level | |
| 0x35 | 2 | humidifier, two status bytes described below | |
| 0x36 | 1 | mask resistance locked | 0 |
| 0x38 | 1 | mask resistance, 0 off or 1 to 5 | 0 |
| 0x39 | 1 | tubing type locked | 0 |
| 0x3b | 1 | tubing type: 0 22 mm, 1 15 mm, 2 15 mm heated | |
| 0x3c | 1 | show AHI and other optional screens, 0 or 0x80 | 0 |
| 0x3e | 1 | auto on, 0 or 0x80 | 0x80 |
| 0x3f | 1 | auto off, 0 or 0x80 | 0 |
| 0x40 | 1 | tubing type, alternate code: 0 22 mm, 1 15 mm, 2 15 mm heated, 3 12 mm | 1, 2 |
| 0x42 | 1 | EZ-Start on auto CPAP | |
| 0x45 | 1 | humidifier target time, DreamStation Go | |
| 0x46 | 1 | tubing type, a third code, as 0x40 plus 4 for 12 mm heated | |

Humidifier status bytes (settings code 0x35, and the two bytes after a mask-on time):

- Byte 1, bits 7 to 5: 0 fixed humidification, 1 adaptive, 2 heated tube, 3 passover, 4 no
  humidifier, 5 error. Bits 4 to 2: humidity level 0 to 5.
- Byte 2, bits 7 to 5: tube temperature 0 to 5. Bits 4 to 2: humidity level again.

When no humidifier is fitted the device still reports level 3 and tube temperature 3. The card
surveyed shows 0x8c 0x6c in all but twelve sessions (no humidifier) and 0x4c 0x6c in those
twelve, which are also the twelve whose tubing type is heated.

## The events file (.002)

Same record form: a code byte, then the size the header block gives. Every record except 0x12
begins with a 16-bit number of seconds elapsed since the previous record; summing gives the
record's time from the session start. The events chunk carries the same start timestamp as the
summary chunk, and its last record lands at the session's duration.

Several event kinds are reported after they happen, with a byte saying how many seconds ago the
event ended. The event's time is the record time minus that. Spans carry a 16-bit duration in
two-second units and are reported after they end.

| Code | Size | Record |
|---|---|---|
| 0x01 | 3 | pressure adjustment: the pressure now delivered. Written at the start, at every auto-titration step, and when the ramp button is pressed |
| 0x02 | 4 | bi-level pressure adjustment: EPAP, IPAP |
| 0x03 | 3 | auto CPAP starting pressure; at the start and end of a session, occasionally mid-session when the device changes the next night's starting pressure |
| 0x04 | 3 | pressure pulse, one byte of unknown meaning |
| 0x05 | 3 | RERA; byte is seconds since it ended |
| 0x06 | 3 | obstructive apnoea; byte is seconds since it was flagged |
| 0x07 | 3 | clear-airway apnoea; byte is seconds since it was flagged |
| 0x0b | 4 | hypopnoea, a rarer variant: one unknown byte, then seconds since it ended |
| 0x0c | 3 | flow limitation; seconds since |
| 0x0d | 2 | vibratory snore, no data |
| 0x0e | 5 | variable breathing: 16-bit duration in two-second units, then seconds since it ended (60 except at a slice end) |
| 0x0f | 5 | periodic breathing: duration in two-second units, seconds since |
| 0x10 | 5 | large leak: duration in two-second units, seconds since |
| 0x11 | 5 | two-minute statistics: total leak in litres per minute, snore count in the interval, average pressure. In single-pressure modes the pressure is the average pressure after pressure relief, which reads as an EPAP; in bi-level modes it is the time-weighted average of both |
| 0x12 | 4 | snores at a pressure, no time field: pressure kind (0 CPAP, 1 EPAP, 2 IPAP), pressure, 16-bit snore count. One per pressure level visited; the counts sum to the statistics word 7 |
| 0x14 | 3 | hypopnoea: byte is its duration in seconds (OSCAR reads it as time since, which places it the same) |
| 0x0a, 0x15 | 3 | hypopnoea variants on other models, not seen here |

The statistics records arrive every 120 seconds while the mask is on, with a short final one at
each mask-off. This card holds 184,000 of them.

Hypopnoea codes: the device's own count in the summary is the number of 0x14 records. The 0x0b
variant (15 on this card against 11,140) is reported separately by this library and is not added
to the device's count.

## What this library computes

- Session start and end as UTC instants from the chunk timestamp and the equipment-off offset.
- Mask-on time as the sum of the mask-on to mask-off spans.
- Event counts and span durations from the events file, kept apart from the device's own counts
  in the statistics record, so a reader can see both and notice when they differ.
- Indexes per hour of mask-on time, from the device's counts: AHI as obstructive plus
  clear-airway plus hypopnoea; RDI as AHI plus RERA. These follow the definitions on the device's
  own reports and in OSCAR; the American Academy of Sleep Medicine's scoring rules define the
  event terms.
- Leak statistics from the two-minute records: mean, 95th percentile and maximum of total leak,
  weighted equally per record. The device's reports show unintentional leak, which needs the
  mask's intentional leak curve and is not attempted here.

Nothing is read from the waveform files.
