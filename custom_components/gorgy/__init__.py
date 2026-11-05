"""The Gorgy Timing integration: control a Gorgy Timing LED clock."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, EVENT_HOMEASSISTANT_CLOSE, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.storage import Store

from .api import GorgyClient, create_session
from .const import STORAGE_VERSION
from .coordinator import GorgyConfigEntry, GorgyCoordinator, storage_key

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: GorgyConfigEntry) -> bool:
    """Set up a clock from a config entry."""
    # Own session instead of Home Assistant's shared one: the clock needs a new
    # connection for every request (see create_session).
    session = create_session()

    async def _close_session(_: Event | None = None) -> None:
        await session.close()

    entry.async_on_unload(_close_session)
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_CLOSE, _close_session))

    client = GorgyClient(session, entry.data[CONF_HOST], entry.data[CONF_PASSWORD])
    coordinator = GorgyCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GorgyConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: GorgyConfigEntry) -> None:
    """Delete the remembered brightness when the clock is removed."""
    await Store(hass, STORAGE_VERSION, storage_key(entry)).async_remove()
