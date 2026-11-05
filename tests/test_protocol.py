"""Wire format, checked against captures from a real clock."""

import pytest

from custom_components.gorgy.protocol import (
    GorgyValidationError,
    apply_display_changes,
    build_display_payload,
    build_stopwatch_action_form,
    build_stopwatch_preset_form,
    describe_display,
    parse_features,
    parse_key_values,
    parse_stopwatch,
    split_chrono_fields,
    utc_offset_quarters,
)

from .conftest import CHRONO_GETDATA, DISPLAY_GETDATA, MENU

# What display.html's onApplyClicked() sends for the settings above
BROWSER_PAYLOAD = "display/index=1/timeAlternationDuration=12/dateAlternationDuration=0/tempAlternationDuration=0/color=0/vaguecolor=0/brightness=5/offset=4/dstPolicy=1/langue=1/dstBegin=0/0/0/0/dstEnd=0/0/0/0/monthAlternationDuration=10/yearAlternationDuration=5/daycolor=0/monthcolor=0/calbrightness=0/syncdots=1/behavdots=0/tenthTemperature=0/brightnessoverride=0"


def test_parse_key_values() -> None:
    raw = parse_key_values(DISPLAY_GETDATA)
    assert raw["brightness"] == "5"
    assert raw["dstBegin"] == ["00", "00", "00", "00"]
    assert raw["tenthTemperature"] == "0"
    assert "".join(parse_key_values("temperature=--.-/°C/x=1")["temperature"]) == "--.-°C"


def test_round_trip_matches_original_web_ui() -> None:
    assert build_display_payload(parse_key_values(DISPLAY_GETDATA)) == BROWSER_PAYLOAD


def test_manual_dst_dates_are_passed_through() -> None:
    raw = {
        **parse_key_values(DISPLAY_GETDATA),
        "dstPolicy": "5",
        "dstBegin": ["03", "31", "01", "00"],
        "dstEnd": ["10", "27", "01", "00"],
    }
    assert "/dstBegin=03/31/01/00/dstEnd=10/27/01/00/" in build_display_payload(raw)


def test_utc_offset_in_quarter_hours() -> None:
    assert utc_offset_quarters({"offsethour": "1", "offsetminute": "0"}) == 4
    assert utc_offset_quarters({"offsethour": "5", "offsetminute": "2"}) == 22  # +5:30
    assert utc_offset_quarters({"offsethour": "-3", "offsetminute": "2"}) == -14  # -3:30


def test_refuses_incomplete_payload() -> None:
    raw = parse_key_values(DISPLAY_GETDATA)
    del raw["syncdots"]
    with pytest.raises(ValueError, match="missing: syncdots"):
        build_display_payload(raw)


def test_describe_display() -> None:
    d = describe_display(parse_key_values(DISPLAY_GETDATA))
    assert d.on
    assert d.brightness == 5
    assert d.max_recommended_brightness == 7
    assert d.digit_color == "red"
    assert d.utc_offset_minutes == 60
    assert d.dst_policy == "europe"
    assert d.dot_mode == "fixed"
    assert d.dot_light == "when-synchronized"
    assert not describe_display({**parse_key_values(DISPLAY_GETDATA), "brightness": "0"}).on


def test_apply_display_changes_validates() -> None:
    raw = parse_key_values(DISPLAY_GETDATA)
    assert apply_display_changes(raw, {"brightness": 0})["brightness"] == "0"
    assert apply_display_changes(raw, {"digit_color": "green"})["color"] == "2"
    assert apply_display_changes(raw, {"brightness": 9, "brightness_override": True})["brightnessoverride"] == "1"
    assert apply_display_changes(raw, {"time_alternation": 3.0})["timeAlternationDuration"] == "3"
    with pytest.raises(GorgyValidationError, match="recommended maximum of 7"):
        apply_display_changes(raw, {"brightness": 8})
    with pytest.raises(GorgyValidationError, match="between 0 and 10"):
        apply_display_changes(raw, {"brightness": 11})
    with pytest.raises(GorgyValidationError, match="integer"):
        apply_display_changes(raw, {"brightness": 2.5})
    with pytest.raises(GorgyValidationError, match="one of: red, amber, green"):
        apply_display_changes(raw, {"digit_color": "purple"})
    with pytest.raises(GorgyValidationError, match="Unknown field"):
        apply_display_changes(raw, {"nope": 1})
    assert raw["brightness"] == "5", "input must not be mutated"


def test_blue_white_models() -> None:
    raw = {**parse_key_values(DISPLAY_GETDATA), "bleublanc": "1"}
    assert describe_display(raw).digit_color == "white"
    assert apply_display_changes(raw, {"digit_color": "blue"})["color"] == "2"


def test_chrono_fields_unescape_slash() -> None:
    assert split_chrono_fields("a/b\\/c/d") == ["a", "b/c", "d"]


def test_parse_stopwatch() -> None:
    sw = parse_stopwatch(CHRONO_GETDATA)
    assert sw.state == "Stopped"
    assert sw.counter.text == "0d 00:00:00"
    assert sw.configurable
    assert sw.last_error is None
    assert sw.start_minutes == 0
    assert [(b.action, b.enabled) for b in sw.buttons] == [
        ("start_up", True),
        ("start_down", True),
        ("pause", False),
        ("display", True),
    ]
    assert sw.available_actions == ("start_up", "start_down", "display")
    assert build_stopwatch_action_form(sw.buttons[0]) == "Value_5=Count+up"


def test_stopwatch_start_value() -> None:
    fields = split_chrono_fields(CHRONO_GETDATA)
    fields[13:17] = ["", "0", "01", "30"]  # start value line visible: 0 d 01:30
    assert parse_stopwatch("/".join(fields)).start_minutes == 90


def test_stopwatch_preset_form() -> None:
    assert build_stopwatch_preset_form(30) == (
        "startDaySet=0&startHourSet=0&startSecSet=0&startMinSet=30&endMinSet=0&Value_0=Apply"
    )
    with pytest.raises(GorgyValidationError, match="between 0 and 99"):
        build_stopwatch_preset_form(100)


def test_features() -> None:
    assert parse_features(MENU) == {"chrono"}
