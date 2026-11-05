"""Switch for brightness levels above the recommended maximum."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GorgyConfigEntry, GorgyCoordinator
from .entity import GorgyEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GorgyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the brightness override switch."""
    async_add_entities([GorgyBrightnessOverrideSwitch(entry.runtime_data)])


class GorgyBrightnessOverrideSwitch(GorgyEntity, SwitchEntity):
    """The "Override maximum recommended brightness" option of the clock's web interface."""

    _attr_translation_key = "brightness_override"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: GorgyCoordinator) -> None:
        super().__init__(coordinator, "brightness_override")

    @property
    def is_on(self) -> bool:
        return self.display.brightness_override

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.client
        await self.coordinator.async_display_command(client.update_display(brightness_override=True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        changes: dict[str, Any] = {"brightness_override": False}
        # like the web UI: step down to the maximum instead of refusing
        if self.display.brightness > self.display.max_recommended_brightness:
            changes["brightness"] = self.display.max_recommended_brightness
        await self.coordinator.async_display_command(self.coordinator.client.update_display(**changes))
