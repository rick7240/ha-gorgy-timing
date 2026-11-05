"""Digit color and colon behavior."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GorgyConfigEntry, GorgyCoordinator
from .entity import GorgyEntity
from .protocol import DOT_LIGHT, DOT_MODES, DisplayState

PARALLEL_UPDATES = 1


def _option(name: str) -> str:
    """Home Assistant option keys use underscores ("when-synchronized" -> "when_synchronized")."""
    return name.replace("-", "_")


def _device_name(option: str) -> str:
    return option.replace("_", "-")


@dataclass(frozen=True, kw_only=True)
class GorgySelectDescription(SelectEntityDescription):
    """Maps a select entity to a display setting."""

    field: str  # keyword of GorgyClient.update_display
    current_fn: Callable[[DisplayState], str]
    options_fn: Callable[[DisplayState], tuple[str, ...]]


SELECTS: tuple[GorgySelectDescription, ...] = (
    GorgySelectDescription(
        key="digit_color",
        translation_key="digit_color",
        field="digit_color",
        current_fn=lambda d: d.digit_color,
        # red/amber/green, or white/cyan/blue on blue-white models
        options_fn=lambda d: d.available_colors,
    ),
    GorgySelectDescription(
        key="dot_mode",
        translation_key="dot_mode",
        entity_category=EntityCategory.CONFIG,
        field="dot_mode",
        current_fn=lambda d: d.dot_mode,
        options_fn=lambda d: DOT_MODES,
    ),
    GorgySelectDescription(
        key="dot_light",
        translation_key="dot_light",
        entity_category=EntityCategory.CONFIG,
        field="dot_light",
        current_fn=lambda d: d.dot_light,
        options_fn=lambda d: DOT_LIGHT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GorgyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the select entities."""
    async_add_entities(GorgySelect(entry.runtime_data, description) for description in SELECTS)


class GorgySelect(GorgyEntity, SelectEntity):
    """A display setting with fixed choices."""

    entity_description: GorgySelectDescription

    def __init__(self, coordinator: GorgyCoordinator, description: GorgySelectDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def options(self) -> list[str]:
        return [_option(name) for name in self.entity_description.options_fn(self.display)]

    @property
    def current_option(self) -> str | None:
        current = _option(self.entity_description.current_fn(self.display))
        return current if current in self.options else None

    async def async_select_option(self, option: str) -> None:
        client = self.coordinator.client
        changes = {self.entity_description.field: _device_name(option)}
        await self.coordinator.async_display_command(client.update_display(**changes))
