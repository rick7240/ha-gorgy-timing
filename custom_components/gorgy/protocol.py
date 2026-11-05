"""Wire format of the Gorgy Timing web interface.

Reverse engineered from display.html / chrono.js of firmware 120.1.8.5
(model GT_LEDI).

Requests and responses are plain text, not form-encoded::

    GET  /display/getdata  -> "brightness=5/maxbrightness=7/dstBegin=00/00/00/00/..."
    POST /display/setdata  <- "display/index=1/brightness=5/..." (always the full set)
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlencode

type RawSettings = dict[str, str | list[str]]


class GorgyValidationError(ValueError):
    """A value is not accepted by the clock."""


def parse_key_values(text: str) -> RawSettings:
    """Parse ``key=value/key=value/`` responses.

    A segment without ``=`` continues the previous key, e.g.
    ``dstBegin=03/31/01/00`` -> ``{"dstBegin": ["03", "31", "01", "00"]}``.
    """
    result: RawSettings = {}
    last_key: str | None = None
    segments = text.split("/")
    for index, segment in enumerate(segments):
        if segment == "" and index == len(segments) - 1:
            continue  # trailing slash
        key, eq, value = segment.partition("=")
        if eq:
            last_key = key
            result[key] = value
        elif last_key is not None:
            previous = result[last_key]
            result[last_key] = [*previous, segment] if isinstance(previous, list) else [previous, segment]
    return result


# ---------------------------------------------------------------------------
# Display configuration
# ---------------------------------------------------------------------------

BRIGHTNESS_MIN = 0
BRIGHTNESS_MAX = 10
ALTERNATION_MAX = 15
COLORS = ("red", "amber", "green")
COLORS_BLUE_WHITE = ("white", "cyan", "blue")  # models with bleublanc=1
DOT_MODES = ("blinking", "fixed")
DOT_LIGHT = ("when-synchronized", "when-not-synchronized", "always")
DST_POLICIES = {"0": "none", "1": "europe", "2": "us-canada", "5": "manual"}

# Calendar fields are only returned by models with a calendar display. The
# browser then submits the form defaults, so we do the same.
CALENDAR_DEFAULTS = {
    "monthAlternationDuration": "10",
    "yearAlternationDuration": "5",
    "daycolor": "0",
    "monthcolor": "0",
    "calbrightness": "0",
}

_LEADING_INT = re.compile(r"\s*([+-]?\d+)")


def _to_int(value: Any) -> int | None:
    """Like JavaScript's parseInt(value, 10): leading integer or None."""
    if isinstance(value, list):
        value = ",".join(value)
    if not isinstance(value, str):
        return None
    match = _LEADING_INT.match(value)
    return int(match.group(1)) if match else None


def _format(value: Any) -> str:
    return ",".join(value) if isinstance(value, list) else str(value)


def palette(raw: RawSettings) -> tuple[str, ...]:
    """Digit colors the model offers."""
    return COLORS_BLUE_WHITE if raw.get("bleublanc") == "1" else COLORS


def utc_offset_quarters(raw: RawSettings) -> int:
    """UTC offset in quarter hours, computed exactly like onApplyClicked() in display.html."""
    hours = _to_int(raw.get("offsethour")) or 0
    quarters = _to_int(raw.get("offsetminute")) or 0
    return hours * 4 + (-abs(quarters) if hours < 0 else quarters)


def build_display_payload(raw: RawSettings) -> str:
    """Build the POST body for /display/setdata from raw settings (as returned by getdata)."""
    s: dict[str, Any] = {**CALENDAR_DEFAULTS, **raw}
    manual_dst = str(s.get("dstPolicy")) == "5"

    def dst(value: Any) -> str:
        if not manual_dst:
            return "0/0/0/0"
        if value is None:
            return ""
        return "/".join(value) if isinstance(value, list) else str(value)

    fields: list[tuple[str, Any]] = [
        ("index", "1"),
        ("timeAlternationDuration", s.get("timeAlternationDuration")),
        ("dateAlternationDuration", s.get("dateAlternationDuration")),
        ("tempAlternationDuration", s.get("tempAlternationDuration")),
        ("color", s.get("color")),
        ("vaguecolor", s.get("vaguecolor")),
        ("brightness", s.get("brightness")),
        ("offset", utc_offset_quarters(s)),
        ("dstPolicy", s.get("dstPolicy")),
        ("langue", s.get("langue")),
        ("dstBegin", dst(s.get("dstBegin"))),
        ("dstEnd", dst(s.get("dstEnd"))),
        ("monthAlternationDuration", s.get("monthAlternationDuration")),
        ("yearAlternationDuration", s.get("yearAlternationDuration")),
        ("daycolor", s.get("daycolor")),
        ("monthcolor", s.get("monthcolor")),
        ("calbrightness", s.get("calbrightness")),
        ("syncdots", s.get("syncdots")),
        ("behavdots", s.get("behavdots")),
        ("tenthTemperature", s.get("tenthTemperature")),
        ("brightnessoverride", s.get("brightnessoverride")),
    ]

    if missing := [key for key, value in fields if value is None]:
        # Never send incomplete settings - the clock would overwrite real ones.
        raise ValueError(f"Display settings incomplete, missing: {', '.join(missing)}")
    return "display/" + "/".join(f"{key}={_format(value)}" for key, value in fields)


@dataclass(frozen=True, slots=True)
class DisplayState:
    """Human friendly view of the raw display settings."""

    on: bool
    brightness: int
    max_recommended_brightness: int
    brightness_override: bool
    digit_color: str
    available_colors: tuple[str, ...]
    time_alternation: int
    date_alternation: int
    temperature_alternation: int
    dot_mode: str
    dot_light: str
    utc_offset_minutes: int
    dst_policy: str


def _name_at(names: tuple[str, ...], value: Any, fallback: str) -> str:
    index = _to_int(value)
    return names[index] if index is not None and 0 <= index < len(names) else fallback


def describe_display(raw: RawSettings) -> DisplayState:
    """Translate raw display settings into a DisplayState."""
    colors = palette(raw)
    brightness = _to_int(raw.get("brightness")) or 0
    return DisplayState(
        on=brightness > 0,
        brightness=brightness,
        max_recommended_brightness=_to_int(raw.get("maxbrightness")) or BRIGHTNESS_MAX,
        brightness_override=raw.get("brightnessoverride") == "1",
        # display.html falls back to the third color for unknown values
        digit_color=_name_at(colors, raw.get("color"), colors[2]),
        available_colors=colors,
        time_alternation=_to_int(raw.get("timeAlternationDuration")) or 0,
        date_alternation=_to_int(raw.get("dateAlternationDuration")) or 0,
        temperature_alternation=_to_int(raw.get("tempAlternationDuration")) or 0,
        dot_mode=_name_at(DOT_MODES, raw.get("syncdots"), _format(raw.get("syncdots"))),
        dot_light=_name_at(DOT_LIGHT, raw.get("behavdots"), _format(raw.get("behavdots"))),
        utc_offset_minutes=utc_offset_quarters(raw) * 15,
        dst_policy=DST_POLICIES.get(_format(raw.get("dstPolicy")), _format(raw.get("dstPolicy"))),
    )


def _int_in_range(value: Any, low: int, high: int, field: str) -> int:
    number: int | None = None
    if isinstance(value, bool):
        number = None
    elif isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif isinstance(value, str):
        try:
            number = int(value.strip())
        except ValueError:
            number = None
    if number is None or not low <= number <= high:
        raise GorgyValidationError(f"{field} must be an integer between {low} and {high}")
    return number


def _boolean(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in ("true", "1") or (isinstance(value, int) and value == 1):
        return True
    if value in ("false", "0") or (isinstance(value, int) and value == 0):
        return False
    raise GorgyValidationError(f"{field} must be a boolean")


def _enum_index(value: Any, names: tuple[str, ...], field: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        index = value
    else:
        lowered = str(value).lower()
        index = names.index(lowered) if lowered in names else -1
    if not 0 <= index < len(names):
        raise GorgyValidationError(f"{field} must be one of: {', '.join(names)}")
    return index


def apply_display_changes(raw: RawSettings, changes: dict[str, Any]) -> RawSettings:
    """Apply friendly changes to raw settings and return a new dict.

    Accepted keys: brightness (0-10), brightness_override (bool), digit_color,
    time_alternation / date_alternation / temperature_alternation (0-15 s),
    dot_mode, dot_light. The input is not modified.
    """
    updated = dict(raw)
    for key, value in changes.items():
        match key:
            case "brightness":
                updated["brightness"] = str(_int_in_range(value, BRIGHTNESS_MIN, BRIGHTNESS_MAX, key))
            case "brightness_override":
                updated["brightnessoverride"] = "1" if _boolean(value, key) else "0"
            case "digit_color":
                updated["color"] = str(_enum_index(value, palette(raw), key))
            case "time_alternation":
                updated["timeAlternationDuration"] = str(_int_in_range(value, 0, ALTERNATION_MAX, key))
            case "date_alternation":
                updated["dateAlternationDuration"] = str(_int_in_range(value, 0, ALTERNATION_MAX, key))
            case "temperature_alternation":
                updated["tempAlternationDuration"] = str(_int_in_range(value, 0, ALTERNATION_MAX, key))
            case "dot_mode":
                updated["syncdots"] = str(_enum_index(value, DOT_MODES, key))
            case "dot_light":
                updated["behavdots"] = str(_enum_index(value, DOT_LIGHT, key))
            case _:
                raise GorgyValidationError(f'Unknown field "{key}"')

    # The web UI disables brightness levels above the recommended maximum unless
    # "Override maximum recommended brightness" is ticked - enforce the same rule.
    brightness = _to_int(updated.get("brightness"))
    maximum = _to_int(updated.get("maxbrightness"))
    if (
        ("brightness" in changes or "brightness_override" in changes)
        and brightness is not None
        and maximum is not None
        and brightness > maximum
        and updated.get("brightnessoverride") != "1"
    ):
        raise GorgyValidationError(
            f"brightness {brightness} exceeds the recommended maximum of {maximum}; "
            "enable the brightness override to allow it"
        )
    return updated


# ---------------------------------------------------------------------------
# Stopwatch (chrono.html / chrono.js)
# ---------------------------------------------------------------------------


def split_chrono_fields(text: str) -> list[str]:
    """/chrono/getdata is positional. ``\\/`` escapes a literal slash inside a value."""
    return text.replace("/", "\v").replace("\\\v", "/").split("\v")


CHRONO_ERRORS: tuple[str | None, ...] = (
    None,
    "Can't update configuration when not idled.",
    "Can't update configuration: Each field of the Start Date must be between 0 and 100 or empty.",
    "Can't update configuration: Start Date is invalid.",
    "Can't update configuration: Invalid combination between Start Value, End Value and End Date.",
    "Can't update configuration: Each field of the Start Value must be between 0 and 100 or empty.",
    "Can't update configuration: Each field of the End Value must be between 0 and 100 or empty.",
    "Can't update configuration: Each field of the End Date must be between 0 and 100 or empty.",
    "Can't update configuration: End Date is invalid.",
    "Can't update configuration: End Date is past.",
)

# Each button is a <form method=post> whose action comes from getdata; the
# submit input's name/value pair is sent along like a browser would.
# The actions are state dependent: while running/paused the first button
# becomes "reset" and the third "resume" - so callers must address actions,
# never button positions.
# (label index, action index, enabled index or None, form field)
CHRONO_BUTTONS: tuple[tuple[int, int, int | None, str], ...] = (
    (38, 40, 41, "Value_5"),  # count up / reset
    (42, 44, 45, "Value_6"),  # count down
    (46, 48, 49, "Value_7"),  # pause / resume
    (55, 57, None, "Value_4"),  # display / mask
)


@dataclass(frozen=True, slots=True)
class StopwatchTime:
    """A counter value of the stopwatch."""

    text: str
    days: int
    hours: int
    minutes: int
    seconds: int


@dataclass(frozen=True, slots=True)
class StopwatchButton:
    """One of the state dependent stopwatch buttons."""

    action: str
    label: str
    enabled: bool
    field: str


@dataclass(frozen=True, slots=True)
class StopwatchState:
    """Parsed /chrono/getdata response."""

    state: str
    device_time: str
    counter: StopwatchTime
    elapsed: StopwatchTime
    started_at: str | None
    ends_at: str | None
    start_minutes: int
    configurable: bool
    last_error: str | None
    display_hint: str | None
    buttons: tuple[StopwatchButton, ...]

    @property
    def available_actions(self) -> tuple[str, ...]:
        """Actions the clock offers right now."""
        return tuple(button.action for button in self.buttons if button.enabled)


def _start_minutes(line: str, days: str, hours: str, minutes: str) -> int:
    """Configured start value (confDayStart/confHourStart/confMinStart in chrono.js).

    The line is "hidden" while no start value is configured - the clock then starts at 0.
    """
    if line == "hidden":
        return 0
    return (_to_int(days) or 0) * 1440 + (_to_int(hours) or 0) * 60 + (_to_int(minutes) or 0)


def parse_stopwatch(text: str) -> StopwatchState:
    """Parse the positional /chrono/getdata format."""
    fields = split_chrono_fields(text)

    def f(index: int) -> str:
        return fields[index] if index < len(fields) else ""

    def time(sign: str, days: str, hours: str, minutes: str, seconds: str) -> StopwatchTime:
        return StopwatchTime(
            text=f"{sign}{_to_int(days) or 0}d {hours or '00'}:{minutes or '00'}:{seconds or '00'}",
            days=_to_int(days) or 0,
            hours=_to_int(hours) or 0,
            minutes=_to_int(minutes) or 0,
            seconds=_to_int(seconds) or 0,
        )

    buttons = tuple(
        StopwatchButton(
            action=f(action),
            label=f(label),
            enabled=bool(f(action)) and (enabled is None or f(enabled) != "0"),
            field=field,
        )
        for label, action, enabled, field in CHRONO_BUTTONS
    )
    error_index = _to_int(f(0))
    return StopwatchState(
        state=f(27),
        device_time=f(1),
        counter=time(f(2), f(6), f(5), f(4), f(3)),
        elapsed=time("", f(10), f(9), f(8), f(7)),
        started_at=f(11) or None,
        ends_at=f(12) or None,
        start_minutes=_start_minutes(f(13), f(14), f(15), f(16)),
        configurable=f(37) != "0",
        last_error=(
            CHRONO_ERRORS[error_index]
            if error_index is not None and 0 <= error_index < len(CHRONO_ERRORS)
            else None
        ),
        display_hint=f(53) or None,
        buttons=buttons,
    )


def build_stopwatch_preset_form(minutes: Any) -> str:
    """Form body of the "basic" stopwatch settings form (start value in minutes)."""
    value = _int_in_range(minutes, 0, 99, "minutes")
    return urlencode(
        {
            "startDaySet": "0",
            "startHourSet": "0",
            "startSecSet": "0",
            "startMinSet": str(value),
            "endMinSet": "0",
            "Value_0": "Apply",
        }
    )


def build_stopwatch_action_form(button: StopwatchButton) -> str:
    """Form body a browser sends when the stopwatch button is clicked."""
    return urlencode({button.field: button.label})


def parse_features(text: str) -> set[str]:
    """Features of the model from GET /menu, e.g. ``chrono=1/temperature=0/...``."""
    return {key for key, value in parse_key_values(text).items() if value == "1"}
