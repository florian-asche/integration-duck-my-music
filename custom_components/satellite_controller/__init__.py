"""Satellite Controller: lowers the music in a room while a voice satellite there is busy.

Planned behavior (see docs/plan.md): when an ESPHome Assist satellite leaves
``idle``, the players that are playing music in the same area are lowered by half
of their own volume, and restored when the satellite is ``idle`` again. This
version only sets the integration up and tears it down.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Satellite Controller from a config entry."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return True
