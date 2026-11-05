"""Stopwatch buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GorgyConfigEntry, GorgyCoordinator
from .entity import GorgyEntity

PARALLEL_UPDATES = 1

# The clock's buttons change their meaning with the state ("count up" becomes
# "reset" while running), so there is one entity per action. An action the
# clock does not offer right now is shown as unavailable.
STOPWATCH_ACTIONS = ("start_up", "start_down", "pause", "resume", "reset", "display", "mask")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GorgyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the stopwatch buttons."""
    coordinator = entry.runtime_data
    if coordinator.has_stopwatch:
        async_add_entities(GorgyStopwatchButton(coordinator, action) for action in STOPWATCH_ACTIONS)


class GorgyStopwatchButton(GorgyEntity, ButtonEntity):
    """Runs one stopwatch action."""

    def __init__(self, coordinator: GorgyCoordinator, action: str) -> None:
        super().__init__(coordinator, f"stopwatch_{action}")
        self._action = action
        self._attr_translation_key = f"stopwatch_{action}"

    @property
    def available(self) -> bool:
        stopwatch = self.stopwatch
        return super().available and stopwatch is not None and self._action in stopwatch.available_actions

    async def async_press(self) -> None:
        client = self.coordinator.client
        await self.coordinator.async_stopwatch_command(client.run_stopwatch_action(self._action))
