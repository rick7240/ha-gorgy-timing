"""Config flow: add, reauthenticate and reconfigure a clock."""

from __future__ import annotations

import pytest

from custom_components.gorgy.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import PASSWORD, SERIAL, FakeClock

pytestmark = pytest.mark.usefixtures("no_setup")


async def _start(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result["flow_id"]


async def test_user_flow(hass: HomeAssistant, fake_clock: FakeClock) -> None:
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: f"http://{fake_clock.host}/", CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Gorgy GT_LEDI"
    assert result["data"] == {CONF_HOST: fake_clock.host, CONF_PASSWORD: PASSWORD}
    assert result["result"].unique_id == SERIAL


@pytest.mark.parametrize(
    ("password", "reachable", "errors"),
    [
        ("wrong", True, {"base": "invalid_auth"}),
        (PASSWORD, False, {"base": "cannot_connect"}),
        ("a/b", True, {CONF_PASSWORD: "unsupported_password"}),
    ],
)
async def test_user_flow_errors_then_recovers(
    hass: HomeAssistant, fake_clock: FakeClock, password: str, reachable: bool, errors: dict[str, str]
) -> None:
    fake_clock.reachable = reachable
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: fake_clock.host, CONF_PASSWORD: password}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors

    fake_clock.reachable = True
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: fake_clock.host, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured_updates_host(hass: HomeAssistant, fake_clock: FakeClock) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={CONF_HOST: "10.0.0.1", CONF_PASSWORD: PASSWORD})
    entry.add_to_hass(hass)
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: fake_clock.host, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == fake_clock.host


async def test_reauth(hass: HomeAssistant, fake_clock: FakeClock, mock_entry: MockConfigEntry) -> None:
    mock_entry.add_to_hass(hass)
    fake_clock.password = "new-password"
    result = await mock_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "still-wrong"})
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "new-password"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_entry.data[CONF_PASSWORD] == "new-password"


async def test_reconfigure(hass: HomeAssistant, fake_clock: FakeClock) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={CONF_HOST: "10.0.0.1", CONF_PASSWORD: PASSWORD})
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: fake_clock.host, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == fake_clock.host


async def test_reconfigure_rejects_other_clock(hass: HomeAssistant, fake_clock: FakeClock) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="999999", data={CONF_HOST: "10.0.0.1", CONF_PASSWORD: PASSWORD})
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: fake_clock.host, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert entry.data[CONF_HOST] == "10.0.0.1"
