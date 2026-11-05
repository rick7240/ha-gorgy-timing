"""Base entity for the Gorgy Timing integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import GorgyCoordinator
from .protocol import DisplayState, StopwatchState


class GorgyEntity(CoordinatorEntity[GorgyCoordinator]):
    """Entity of one clock."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GorgyCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        status = coordinator.data.status
        device_id = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            connections={(CONNECTION_NETWORK_MAC, format_mac(status.mac))} if status.mac else set(),
            manufacturer=MANUFACTURER,
            model=status.device_name,
            name=entry.title,
            serial_number=status.serial_number,
            sw_version=status.firmware,
            hw_version=status.hardware,
            configuration_url=f"http://{coordinator.client.host}",
        )

    @property
    def display(self) -> DisplayState:
        """Display settings as last reported by the clock."""
        return self.coordinator.data.display

    @property
    def stopwatch(self) -> StopwatchState | None:
        """Stopwatch state as last reported by the clock."""
        return self.coordinator.data.stopwatch
