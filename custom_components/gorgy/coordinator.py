"""Polls the clock and runs commands for the entities."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass, replace
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeviceStatus, GorgyAuthError, GorgyClient, GorgyError, GorgyStateError
from .const import DOMAIN, FEATURE_STOPWATCH, SCAN_INTERVAL, STORAGE_VERSION
from .protocol import DisplayState, GorgyValidationError, StopwatchState

_LOGGER = logging.getLogger(__name__)

type GorgyConfigEntry = ConfigEntry[GorgyCoordinator]


@dataclass(frozen=True, slots=True)
class GorgyData:
    """Everything the entities show."""

    status: DeviceStatus
    display: DisplayState
    stopwatch: StopwatchState | None  # None for models without stopwatch


def storage_key(entry: ConfigEntry) -> str:
    """Store holding the brightness to restore on "turn on"."""
    return f"{DOMAIN}.{entry.entry_id}"


class GorgyCoordinator(DataUpdateCoordinator[GorgyData]):
    """Fetches status, display settings and stopwatch of one clock."""

    config_entry: GorgyConfigEntry

    def __init__(self, hass: HomeAssistant, entry: GorgyConfigEntry, client: GorgyClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.has_stopwatch = False
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, storage_key(entry))
        self._saved_brightness: int | None = None

    async def _async_setup(self) -> None:
        """Runs once before the first refresh."""
        stored = await self._store.async_load() or {}
        if isinstance(last := stored.get("last_brightness"), int) and last > 0:
            self.client.last_brightness = self._saved_brightness = last
        try:
            features = await self.client.get_features()
        except GorgyError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self.has_stopwatch = FEATURE_STOPWATCH in features

    async def _async_update_data(self) -> GorgyData:
        try:
            status = await self.client.get_status()
            display = await self.client.get_display()
            stopwatch = await self.client.get_stopwatch() if self.has_stopwatch else None
        except GorgyAuthError as err:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="invalid_auth") from err
        except GorgyError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self._async_save_brightness()
        return GorgyData(status=status, display=display, stopwatch=stopwatch)

    async def _async_save_brightness(self) -> None:
        brightness = self.client.last_brightness
        if brightness is not None and brightness != self._saved_brightness:
            self._saved_brightness = brightness
            await self._store.async_save({"last_brightness": brightness})

    async def _async_execute[T](self, command: Awaitable[T]) -> T:
        """Run a command and turn clock errors into Home Assistant errors."""
        try:
            return await command
        except GorgyValidationError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
                translation_placeholders={"error": str(err)},
            ) from err
        except GorgyStateError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="not_possible_now",
                translation_placeholders={"error": str(err)},
            ) from err
        except GorgyAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="invalid_auth") from err
        except GorgyError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err
        finally:
            await self._async_save_brightness()

    async def async_display_command(self, command: Awaitable[DisplayState]) -> None:
        """Run a display command and show the settings the clock reports afterwards."""
        display = await self._async_execute(command)
        self.async_set_updated_data(replace(self.data, display=display))

    async def async_stopwatch_command(self, command: Awaitable[StopwatchState]) -> None:
        """Run a stopwatch command and show the state the clock reports afterwards."""
        stopwatch = await self._async_execute(command)
        self.async_set_updated_data(replace(self.data, stopwatch=stopwatch))
