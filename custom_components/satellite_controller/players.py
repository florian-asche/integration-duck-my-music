"""Reads the media players and the effective area of an entity from Home Assistant.

This is the only place that turns Home Assistant's states and registries into
the snapshots that ducking.py plans with.
"""

from __future__ import annotations

from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import PLAYER_PLATFORMS
from .ducking import PlayerSnapshot


def collect_players(hass: HomeAssistant) -> list[PlayerSnapshot]:
    """Snapshots of every ESPHome and Music Assistant media player, in any area."""
    registry = er.async_get(hass)
    players = []
    for state in hass.states.async_all("media_player"):
        entry = registry.async_get(state.entity_id)
        if entry is None or entry.platform not in PLAYER_PLATFORMS:
            continue
        volume = state.attributes.get("volume_level")
        features = state.attributes.get("supported_features") or 0
        players.append(
            PlayerSnapshot(
                entity_id=state.entity_id,
                area_id=er.async_get_effective_area_id(hass, entry),
                device_id=entry.device_id,
                playing=state.state == "playing",
                volume=float(volume) if volume is not None else None,
                can_set_volume=bool(features & MediaPlayerEntityFeature.VOLUME_SET),
                group_members=tuple(state.attributes.get("group_members") or ()),
            )
        )
    return players


def current_volumes(hass: HomeAssistant, entity_ids: list[str]) -> dict[str, float | None]:
    """The current volume of each player, ``None`` if it is unavailable or has none."""
    volumes: dict[str, float | None] = {}
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        volume = state.attributes.get("volume_level") if state is not None else None
        volumes[entity_id] = float(volume) if volume is not None else None
    return volumes
