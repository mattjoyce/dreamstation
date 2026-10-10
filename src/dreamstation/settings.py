"""The therapy settings record inside a summary (summary record code 1).

A nested sequence of code, length, value. The table of codes is in docs/FORMAT.md under
"Settings". Pressures are kept in tenths of a centimetre of water as the device writes them;
``Settings.pressure_cmh2o`` style helpers are deliberately absent so that nothing is rounded
twice. Divide by ten at the edge.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import FormatError

MODES = {0: "cpap", 1: "bilevel", 2: "auto_cpap", 3: "auto_bilevel", 4: "cpap_check"}
TUBING = {0: 22, 1: 15, 2: 15, 3: 12, 4: 12}
HEATED_TUBING = {2, 4}
HUMIDIFIER_MODES = {
    0: "fixed",
    1: "adaptive",
    2: "heated_tube",
    3: "passover",
    4: "none",
    5: "error",
}

# Settings whose single value byte is a flag: 0 off, 0x80 on.
_FLAGS = {
    0x2A: "ez_start",
    0x2F: "flex_locked",
    0x36: "mask_resistance_locked",
    0x39: "tubing_locked",
    0x3C: "show_ahi",
    0x3E: "auto_on",
    0x3F: "auto_off",
    0x42: "ez_start",
}


@dataclass(frozen=True)
class Humidifier:
    """Humidifier status, from the two status bytes the device writes in several places."""

    mode: str
    level: int
    tube_temperature: int
    present: bool

    @classmethod
    def from_bytes(cls, b1: int, b2: int) -> Humidifier:
        mode_code = b1 >> 5
        if mode_code not in HUMIDIFIER_MODES:
            raise FormatError(f"humidifier mode {mode_code} is not known")
        mode = HUMIDIFIER_MODES[mode_code]
        return cls(
            mode=mode,
            level=(b1 >> 2) & 7,
            tube_temperature=(b2 >> 5) & 7,
            present=mode != "none",
        )


@dataclass
class Settings:
    """The settings in force for a session, as the device reported them."""

    mode: str
    pressure: int | None = None  # fixed CPAP pressure
    pressure_min: int | None = None  # auto CPAP range, or CPAP-Check range
    pressure_max: int | None = None
    epap: int | None = None  # bi-level
    ipap: int | None = None
    epap_min: int | None = None  # auto bi-level
    ipap_max: int | None = None
    pressure_support_min: int | None = None
    pressure_support_max: int | None = None
    auto_trial_days: int | None = None
    ramp_type: str | None = None  # linear, smart, plus
    ramp_minutes: int | None = None
    ramp_pressure: int | None = None
    flex_mode: str | None = None  # off, c_flex, c_flex_plus, a_flex, bi_flex, rise_time, p_flex
    flex_level: int | None = None
    humidifier: Humidifier | None = None
    humidifier_target_hours: float | None = None
    tubing_mm: int | None = None
    tubing_heated: bool | None = None
    mask_resistance: int | None = None
    comfort_flags: int | None = None  # the raw second byte of code 1, see FORMAT.md
    flags: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_bytes(
        cls, data: bytes, *, path: str | None = None, session: int | None = None
    ) -> Settings:
        """Decode a settings record. Stops on a code the format note does not list."""
        pos = 0
        mode: str | None = None
        s: Settings | None = None
        ramp_type_seen = False
        while pos + 2 <= len(data):
            code, length = data[pos], data[pos + 1]
            value = data[pos + 2 : pos + 2 + length]
            if len(value) != length:
                raise FormatError(
                    f"setting {code:#04x} runs past the record", path=path, session=session
                )
            pos += 2 + length
            if code == 0x00:
                if value[0] not in MODES:
                    raise FormatError(
                        f"therapy mode {value[0]} is not known", path=path, session=session
                    )
                mode = MODES[value[0]]
                s = cls(mode=mode)
                continue
            if s is None:
                raise FormatError(
                    "settings do not start with the therapy mode", path=path, session=session
                )
            if code == 0x01:
                s.comfort_flags = value[1] if length >= 2 else None
            elif code == 0x0A:
                s.pressure = value[0]
            elif code == 0x0C:
                s.pressure_min, s.pressure_max, s.pressure = value[0], value[1], value[2]
            elif code == 0x0D:
                s.pressure_min, s.pressure_max = value[0], value[1]
            elif code == 0x0E:
                s.epap, s.ipap = value[0], value[1]
            elif code == 0x0F:
                s.epap_min, s.ipap_max = value[0], value[1]
                s.pressure_support_min, s.pressure_support_max = value[2], value[3]
            elif code == 0x10:
                s.auto_trial_days, s.pressure_min, s.pressure_max = value[0], value[1], value[2]
            elif code == 0x2B:
                s.ramp_type = "smart" if value[0] else "linear"
                ramp_type_seen = True
            elif code == 0x2C:
                s.ramp_minutes = value[0]
                if not ramp_type_seen:
                    s.ramp_type = "plus"
            elif code == 0x2D:
                s.ramp_pressure = value[0]
            elif code == 0x2E:
                s.flex_mode = _flex_mode(value[0], s.mode, path, session)
            elif code == 0x30:
                s.flex_level = value[0]
            elif code == 0x35:
                s.humidifier = Humidifier.from_bytes(value[0], value[1])
            elif code == 0x38:
                s.mask_resistance = value[0]
            elif code in (0x3B, 0x40, 0x46):
                if value[0] not in TUBING:
                    raise FormatError(
                        f"tubing type {value[0]} is not known", path=path, session=session
                    )
                s.tubing_mm = TUBING[value[0]]
                s.tubing_heated = value[0] in HEATED_TUBING
            elif code == 0x45:
                s.humidifier_target_hours = value[0] / 10 if value[0] > 1 else None
            elif code in _FLAGS:
                s.flags[_FLAGS[code]] = bool(value[0])
            else:
                raise FormatError(
                    f"setting code {code:#04x} is not known", path=path, session=session
                )
        if s is None:
            raise FormatError("empty settings record", path=path, session=session)
        return s


def _flex_mode(value: int, mode: str, path: str | None, session: int | None) -> str:
    single = mode in ("cpap", "cpap_check", "auto_cpap")
    if value == 0x00:
        return "off"
    if value == 0x80:
        return "c_flex" if single else "bi_flex"
    if value == 0x90:
        return "a_flex" if mode == "auto_cpap" else "c_flex_plus"
    if value == 0xA0:
        return "rise_time"
    if value == 0xB0:
        return "p_flex"
    raise FormatError(
        f"pressure relief value {value:#04x} is not known", path=path, session=session
    )
