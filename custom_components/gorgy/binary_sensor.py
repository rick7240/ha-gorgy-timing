"""NTP synchronization state."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GorgyConfigEntry, GorgyCoordinator
from .entity import GorgyEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GorgyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor."""
    async_add_entities([GorgyNtpSynchronizedSensor(entry.runtime_data)])


class GorgyNtpSynchronizedSensor(GorgyEntity, BinarySensorEntity):
    """On while the clock is synchronized with its NTP server."""

    _attr_translation_key = "ntp_synchronized"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: GorgyCoordinator) -> None:
        super().__init__(coordinator, "ntp_synchronized")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.status.synchronized
