"""Display durations and the stopwatch start value."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import GorgyConfigEntry, GorgyCoordinator, GorgyData
from .entity import GorgyEntity
from .protocol import ALTERNATION_MAX

PARALLEL_UPDATES = 1


async def _set_time_alternation(coordinator: GorgyCoordinator, value: int) -> None:
    _ensure_time_or_date(value, coordinator.data.display.date_alternation)
    await coordinator.async_display_command(coordinator.client.update_display(time_alternation=value))


async def _set_date_alternation(coordinator: GorgyCoordinator, value: int) -> None:
    _ensure_time_or_date(value, coordinator.data.display.time_alternation)
    await coordinator.async_display_command(coordinator.client.update_display(date_alternation=value))


def _ensure_time_or_date(value: int, other: int) -> None:
    """The clock's web UI does not allow hiding both time and date."""
    if value == 0 and other == 0:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="time_and_date_hidden")


async def _set_stopwatch_preset(coordinator: GorgyCoordinator, value: int) -> None:
    await coordinator.async_stopwatch_command(coordinator.client.set_stopwatch_preset(value))


@dataclass(frozen=True, kw_only=True)
class GorgyNumberDescription(NumberEntityDescription):
    """Maps a number entity to a clock setting."""

    value_fn: Callable[[GorgyData], int | None]
    set_fn: Callable[[GorgyCoordinator, int], Awaitable[None]]
    stopwatch: bool = False


NUMBERS: tuple[GorgyNumberDescription, ...] = (
    GorgyNumberDescription(
        key="time_alternation",
        translation_key="time_alternation",
        entity_category=EntityCategory.CONFIG,
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        native_min_value=0,
        native_max_value=ALTERNATION_MAX,
        native_step=1,
        value_fn=lambda data: data.display.time_alternation,
        set_fn=_set_time_alternation,
    ),
    GorgyNumberDescription(
        key="date_alternation",
        translation_key="date_alternation",
        entity_category=EntityCategory.CONFIG,
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        native_min_value=0,
        native_max_value=ALTERNATION_MAX,
        native_step=1,
        value_fn=lambda data: data.display.date_alternation,
        set_fn=_set_date_alternation,
    ),
    GorgyNumberDescription(
        key="stopwatch_preset",
        translation_key="stopwatch_preset",
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        native_min_value=0,
        native_max_value=99,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=lambda data: data.stopwatch.start_minutes if data.stopwatch else None,
        set_fn=_set_stopwatch_preset,
        stopwatch=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GorgyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        GorgyNumber(coordinator, description)
        for description in NUMBERS
        if coordinator.has_stopwatch or not description.stopwatch
    )


class GorgyNumber(GorgyEntity, NumberEntity):
    """A numeric clock setting."""

    entity_description: GorgyNumberDescription

    def __init__(self, coordinator: GorgyCoordinator, description: GorgyNumberDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | None:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        await self.entity_description.set_fn(self.coordinator, round(value))
