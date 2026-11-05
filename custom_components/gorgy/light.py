"""The LED display as a dimmable light."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.color import brightness_to_value, value_to_brightness

from .coordinator import GorgyConfigEntry, GorgyCoordinator
from .entity import GorgyEntity
from .protocol import BRIGHTNESS_MAX

# Clock levels 1..10 (0 = display off)
BRIGHTNESS_SCALE = (1, BRIGHTNESS_MAX)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GorgyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the display light."""
    async_add_entities([GorgyDisplayLight(entry.runtime_data)])


class GorgyDisplayLight(GorgyEntity, LightEntity):
    """On/off and brightness of the LED display. Brightness 0 switches it off."""

    _attr_translation_key = "display"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator: GorgyCoordinator) -> None:
        super().__init__(coordinator, "display")

    @property
    def is_on(self) -> bool:
        return self.display.on

    @property
    def brightness(self) -> int | None:
        if not self.display.on:
            return None
        return value_to_brightness(BRIGHTNESS_SCALE, self.display.brightness)

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.client
        if ATTR_BRIGHTNESS not in kwargs:
            # restores the brightness from before "off"
            await self.coordinator.async_display_command(client.turn_on())
            return
        level = max(1, math.ceil(brightness_to_value(BRIGHTNESS_SCALE, kwargs[ATTR_BRIGHTNESS])))
        if not self.display.brightness_override:
            # Levels above the recommended maximum need the override switch,
            # so 100 % means "as bright as allowed".
            level = min(level, self.display.max_recommended_brightness)
        await self.coordinator.async_display_command(client.update_display(brightness=level))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_display_command(self.coordinator.client.turn_off())
