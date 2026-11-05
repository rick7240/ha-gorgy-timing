"""Stopwatch state and NTP server."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GorgyConfigEntry, GorgyCoordinator
from .entity import GorgyEntity

PARALLEL_UPDATES = 0

# "Counting up" -> "counting_up"
STOPWATCH_STATES = ["stopped", "paused", "counting_up", "counting_down"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GorgyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [GorgyNtpServerSensor(coordinator)]
    if coordinator.has_stopwatch:
        entities.append(GorgyStopwatchStateSensor(coordinator))
    async_add_entities(entities)


class GorgyStopwatchStateSensor(GorgyEntity, SensorEntity):
    """Stopped, paused, counting up or down."""

    _attr_translation_key = "stopwatch_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STOPWATCH_STATES

    def __init__(self, coordinator: GorgyCoordinator) -> None:
        super().__init__(coordinator, "stopwatch_state")

    @property
    def native_value(self) -> str | None:
        if self.stopwatch is None:
            return None
        state = self.stopwatch.state.lower().replace(" ", "_")
        return state if state in STOPWATCH_STATES else None


class GorgyNtpServerSensor(GorgyEntity, SensorEntity):
    """NTP server the clock synchronizes with."""

    _attr_translation_key = "ntp_server"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: GorgyCoordinator) -> None:
        super().__init__(coordinator, "ntp_server")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.status.ntp_server
