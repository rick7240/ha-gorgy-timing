"""Entities against the fake clock."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.gorgy.coordinator import storage_key
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util.color import value_to_brightness
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import FakeClock

LIGHT = "light.gorgy_gt_ledi_display"
OVERRIDE = "switch.gorgy_gt_ledi_override_maximum_brightness"
COLOR = "select.gorgy_gt_ledi_digit_color"
DOT_LIGHT = "select.gorgy_gt_ledi_colon_lights_up"
TIME_DURATION = "number.gorgy_gt_ledi_time_display_duration"
DATE_DURATION = "number.gorgy_gt_ledi_date_display_duration"
PRESET = "number.gorgy_gt_ledi_stopwatch_start_value"
STOPWATCH = "sensor.gorgy_gt_ledi_stopwatch"
COUNT_UP = "button.gorgy_gt_ledi_stopwatch_count_up"
PAUSE = "button.gorgy_gt_ledi_stopwatch_pause"
RESUME = "button.gorgy_gt_ledi_stopwatch_resume"
SYNCED = "binary_sensor.gorgy_gt_ledi_ntp_synchronized"

pytestmark = pytest.mark.usefixtures("setup_entry")


async def _call(hass: HomeAssistant, domain: str, service: str, entity_id: str, **data: Any) -> None:
    await hass.services.async_call(domain, service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True)


def _state(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    assert state is not None, f"{entity_id} does not exist"
    return state.state


async def test_initial_states(hass: HomeAssistant) -> None:
    light = hass.states.get(LIGHT)
    assert light.state == STATE_ON
    assert light.attributes[ATTR_BRIGHTNESS] == value_to_brightness((1, 10), 5)
    assert _state(hass, OVERRIDE) == STATE_OFF
    assert _state(hass, COLOR) == "red"
    assert hass.states.get(COLOR).attributes["options"] == ["red", "amber", "green"]
    assert _state(hass, DOT_LIGHT) == "when_synchronized"
    assert _state(hass, "select.gorgy_gt_ledi_colon") == "fixed"
    assert _state(hass, TIME_DURATION) == "12"
    assert _state(hass, DATE_DURATION) == "0"
    assert _state(hass, PRESET) == "0"
    assert _state(hass, STOPWATCH) == "stopped"
    assert _state(hass, COUNT_UP) != STATE_UNAVAILABLE
    assert _state(hass, PAUSE) == STATE_UNAVAILABLE
    assert _state(hass, SYNCED) == STATE_ON
    assert _state(hass, "sensor.gorgy_gt_ledi_ntp_server").startswith("0.de.pool.ntp.org")


async def test_off_and_on_restores_brightness(hass: HomeAssistant, fake_clock: FakeClock, hass_storage, setup_entry) -> None:
    await _call(hass, "light", "turn_off", LIGHT)
    assert fake_clock.display["brightness"] == "0"
    assert _state(hass, LIGHT) == STATE_OFF
    assert hass_storage[storage_key(setup_entry)]["data"] == {"last_brightness": 5}

    await _call(hass, "light", "turn_on", LIGHT)
    assert fake_clock.display["brightness"] == "5"
    assert _state(hass, LIGHT) == STATE_ON


async def test_payload_is_the_web_ui_format(hass: HomeAssistant, fake_clock: FakeClock) -> None:
    await _call(hass, "light", "turn_off", LIGHT)
    assert fake_clock.display_posts == [
        "display/index=1/timeAlternationDuration=12/dateAlternationDuration=0/tempAlternationDuration=0/color=0/vaguecolor=0/brightness=0/offset=4/dstPolicy=1/langue=1/dstBegin=0/0/0/0/dstEnd=0/0/0/0/monthAlternationDuration=10/yearAlternationDuration=5/daycolor=0/monthcolor=0/calbrightness=0/syncdots=1/behavdots=0/tenthTemperature=0/brightnessoverride=0"
    ]


async def test_full_brightness_respects_recommended_maximum(hass: HomeAssistant, fake_clock: FakeClock) -> None:
    await _call(hass, "light", "turn_on", LIGHT, brightness=255)
    assert fake_clock.display["brightness"] == "7"

    await _call(hass, "switch", "turn_on", OVERRIDE)
    await _call(hass, "light", "turn_on", LIGHT, brightness=255)
    assert fake_clock.display["brightness"] == "10"

    # switching the override off steps down to the maximum, like the web UI
    await _call(hass, "switch", "turn_off", OVERRIDE)
    assert fake_clock.display["brightnessoverride"] == "0"
    assert fake_clock.display["brightness"] == "7"


async def test_lowest_brightness_keeps_display_on(hass: HomeAssistant, fake_clock: FakeClock) -> None:
    await _call(hass, "light", "turn_on", LIGHT, brightness=1)
    assert fake_clock.display["brightness"] == "1"


async def test_select_color_and_colon(hass: HomeAssistant, fake_clock: FakeClock) -> None:
    await _call(hass, "select", "select_option", COLOR, option="green")
    assert fake_clock.display["color"] == "2"
    assert _state(hass, COLOR) == "green"

    await _call(hass, "select", "select_option", DOT_LIGHT, option="always")
    assert fake_clock.display["behavdots"] == "2"


async def test_durations(hass: HomeAssistant, fake_clock: FakeClock) -> None:
    await _call(hass, "number", "set_value", DATE_DURATION, value=4)
    assert fake_clock.display["dateAlternationDuration"] == "4"
    assert _state(hass, DATE_DURATION) == "4"

    await _call(hass, "number", "set_value", DATE_DURATION, value=0)
    with pytest.raises(ServiceValidationError):
        await _call(hass, "number", "set_value", TIME_DURATION, value=0)
    assert fake_clock.display["timeAlternationDuration"] == "12"


async def test_stopwatch_buttons(hass: HomeAssistant, fake_clock: FakeClock) -> None:
    await _call(hass, "button", "press", COUNT_UP)
    assert fake_clock.chrono_posts == [("start_up", "Value_5=Count+up")]
    assert _state(hass, STOPWATCH) == "counting_up"
    assert _state(hass, COUNT_UP) == STATE_UNAVAILABLE
    assert _state(hass, PAUSE) != STATE_UNAVAILABLE

    await _call(hass, "button", "press", PAUSE)
    assert _state(hass, STOPWATCH) == "paused"
    assert _state(hass, RESUME) != STATE_UNAVAILABLE


async def test_stale_button_is_refused(hass: HomeAssistant, fake_clock: FakeClock) -> None:
    """The stopwatch was started elsewhere: "count up" must not turn into a reset."""
    f = fake_clock.chrono
    f[27], f[38], f[40] = "Counting up", "Reset", "reset"
    with pytest.raises(ServiceValidationError):
        await _call(hass, "button", "press", COUNT_UP)
    assert fake_clock.chrono_posts == []


async def test_stopwatch_preset(hass: HomeAssistant, fake_clock: FakeClock) -> None:
    await _call(hass, "number", "set_value", PRESET, value=30)
    assert fake_clock.chrono_posts == [
        ("set_bound_times", "startDaySet=0&startHourSet=0&startSecSet=0&startMinSet=30&endMinSet=0&Value_0=Apply")
    ]
    assert _state(hass, PRESET) == "30"


async def test_unreachable_clock(hass: HomeAssistant, fake_clock: FakeClock, setup_entry: MockConfigEntry) -> None:
    fake_clock.reachable = False
    await setup_entry.runtime_data.async_refresh()
    assert _state(hass, LIGHT) == STATE_UNAVAILABLE

    fake_clock.reachable = True
    await setup_entry.runtime_data.async_refresh()
    assert _state(hass, LIGHT) == STATE_ON


async def test_password_changed_on_clock_starts_reauth(
    hass: HomeAssistant, fake_clock: FakeClock, setup_entry: MockConfigEntry
) -> None:
    fake_clock.password, fake_clock.token = "changed", "another-token"
    await setup_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler("gorgy")
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_relogin_after_token_expired(hass: HomeAssistant, fake_clock: FakeClock, setup_entry: MockConfigEntry) -> None:
    logins = fake_clock.logins
    fake_clock.token = "rotated-token"
    await setup_entry.runtime_data.async_refresh()
    assert fake_clock.logins == logins + 1
    assert _state(hass, LIGHT) == STATE_ON


async def test_unload(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    assert setup_entry.state is ConfigEntryState.NOT_LOADED
