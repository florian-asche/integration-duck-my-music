"""Reads the media players and the effective area of an entity from Home Assistant.

This is the only place that turns Home Assistant's states and registries into
the snapshots that ducking.py plans with.
"""

from __future__ import annotations

import logging

from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import PLAYER_PLATFORMS
from .ducking import CurrentPlayer, PlayerSnapshot

_LOGGER = logging.getLogger(__name__)


def collect_players(hass: HomeAssistant) -> list[PlayerSnapshot]:
    """Snapshots of every ESPHome and Music Assistant media player, in any area."""
    registry = er.async_get(hass)
    players = []
    for state in hass.states.async_all("media_player"):
        entry = registry.async_get(state.entity_id)
        if entry is None or entry.platform not in PLAYER_PLATFORMS:
            _LOGGER.debug(
                "Ignoring media player '%s': %s",
                state.entity_id,
                "it is not in the entity registry" if entry is None else f"platform '{entry.platform}' is not one of {sorted(PLAYER_PLATFORMS)}",
            )
            continue
        volume = state.attributes.get("volume_level")
        features = state.attributes.get("supported_features") or 0
        snapshot = PlayerSnapshot(
            entity_id=state.entity_id,
            area_id=er.async_get_effective_area_id(hass, entry),
            device_id=entry.device_id,
            playing=state.state == "playing",
            volume=float(volume) if volume is not None else None,
            can_set_volume=bool(features & MediaPlayerEntityFeature.VOLUME_SET),
            can_pause=bool(features & MediaPlayerEntityFeature.PAUSE),
            group_members=tuple(state.attributes.get("group_members") or ()),
        )
        _LOGGER.debug(
            "Media player '%s' (%s): state %s, area %s, volume %s, volume control %s, pause %s, group members %s",
            snapshot.entity_id,
            entry.platform,
            state.state,
            snapshot.area_id,
            snapshot.volume,
            snapshot.can_set_volume,
            snapshot.can_pause,
            list(snapshot.group_members),
        )
        players.append(snapshot)
    _LOGGER.debug("Found %d ESPHome and Music Assistant media players", len(players))
    return players


def current_players(hass: HomeAssistant, entity_ids: list[str]) -> dict[str, CurrentPlayer]:
    """The current state and volume of each player, ``None`` where it is unavailable or has none."""
    players: dict[str, CurrentPlayer] = {}
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        volume = state.attributes.get("volume_level") if state is not None else None
        players[entity_id] = CurrentPlayer(state.state if state is not None else None, float(volume) if volume is not None else None)
    return players
