"""Satellite Controller: lowers the music in a room while a voice satellite there is busy.

When an ESPHome Assist satellite leaves ``idle``, the ESPHome and Music
Assistant players that are playing in the same area are lowered by half of their
own volume, and restored when the satellite is ``idle`` again. See docs/plan.md.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .controller import SatelliteController

type SatelliteControllerConfigEntry = ConfigEntry[SatelliteController]


async def async_setup_entry(hass: HomeAssistant, entry: SatelliteControllerConfigEntry) -> bool:
    """Set up Satellite Controller from a config entry."""
    controller = SatelliteController(hass, entry)
    await controller.async_start()
    entry.runtime_data = controller
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SatelliteControllerConfigEntry) -> bool:
    """Unload a config entry and restore the lowered players."""
    await entry.runtime_data.async_stop()
    return True


async def _async_reload(hass: HomeAssistant, entry: SatelliteControllerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
