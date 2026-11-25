"""Plans how to lower and restore the music of the players in a room.

Everything here is a pure function over snapshots of the players: no Home
Assistant access, no service calls. The controller reads the snapshots, calls
these functions and applies the returned actions.

Players that are in the same group are lowered as one unit, through a single
device of the group, because changing the volume of one member can change the
others as well.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

VOLUME_TOLERANCE = 0.02


@dataclass(frozen=True)
class PlayerSnapshot:
    """What is known about one media player at the moment of planning."""

    entity_id: str
    area_id: str | None
    device_id: str | None
    playing: bool
    volume: float | None
    can_set_volume: bool
    group_members: tuple[str, ...] = ()


@dataclass(frozen=True)
class VolumeAction:
    """Set a player to this volume (0..1)."""

    entity_id: str
    volume: float


@dataclass(frozen=True)
class DuckedPlayer:
    """A player that was lowered, and the areas that are keeping it lowered."""

    entity_id: str
    original_volume: float
    ducked_volume: float
    areas: frozenset[str]


@dataclass(frozen=True)
class DuckPlan:
    """The volume changes to apply and the lowered players afterwards."""

    actions: tuple[VolumeAction, ...]
    ducked: Mapping[str, DuckedPlayer]


def plan_duck(
    players: Collection[PlayerSnapshot],
    area_id: str,
    duck_fraction: float,
    excluded_entities: Collection[str],
    excluded_devices: Collection[str],
    ducked: Mapping[str, DuckedPlayer],
    skip_multi_room_groups: bool,
) -> DuckPlan:
    """
    Plan lowering the music in an area.
    :param players: Snapshots of all players that may be lowered, in any area.
    :param area_id: The area whose satellite became busy.
    :param duck_fraction: How much of its own volume each player loses (0.5 halves it).
    :param excluded_entities: Players that are never lowered.
    :param excluded_devices: Devices whose players are never lowered, such as the busy satellite itself.
    :param ducked: The players that are lowered already.
    :param skip_multi_room_groups: Leave groups alone that have members in other areas.
    :return: The volume changes to apply and the lowered players afterwards. Calling it again with the
        result as ``ducked`` changes nothing.
    """
    result = dict(ducked)
    actions: list[VolumeAction] = []
    for group in _groups(players):
        if _is_ducked(group, result):
            result = _keep_ducked(group, result, area_id)
            continue
        target = _select_target(group, area_id, excluded_entities, excluded_devices)
        if target is None or target.volume is None or target.volume <= 0:
            continue
        if skip_multi_room_groups and _spans_other_areas(group, area_id):
            _LOGGER.debug("Group of '%s' has members outside area '%s', skipped", target.entity_id, area_id)
            continue
        ducked_volume = round(target.volume * (1 - duck_fraction), 4)
        _LOGGER.debug("Lowering '%s' in area '%s' from %.2f to %.2f", target.entity_id, area_id, target.volume, ducked_volume)
        actions.append(VolumeAction(target.entity_id, ducked_volume))
        result[target.entity_id] = DuckedPlayer(target.entity_id, target.volume, ducked_volume, frozenset({area_id}))
    return DuckPlan(actions=tuple(actions), ducked=result)


def plan_release(area_id: str | None, ducked: Mapping[str, DuckedPlayer], current_volumes: Mapping[str, float | None]) -> DuckPlan:
    """
    Plan restoring the music of an area, or of all areas.
    :param area_id: The area whose satellite is quiet again, ``None`` for all areas.
    :param ducked: The players that are lowered.
    :param current_volumes: The current volume of each player, ``None`` if it has none.
    :return: The volume changes to apply and the players that stay lowered. A player that another area
        still keeps lowered stays. A player whose volume was changed by someone else is not restored.
    """
    remaining: dict[str, DuckedPlayer] = {}
    actions: list[VolumeAction] = []
    for entity_id, player in ducked.items():
        areas = player.areas - {area_id} if area_id is not None else frozenset()
        if areas:
            remaining[entity_id] = DuckedPlayer(entity_id, player.original_volume, player.ducked_volume, areas)
            continue
        current = current_volumes.get(entity_id)
        if current is not None and abs(current - player.ducked_volume) <= VOLUME_TOLERANCE:
            _LOGGER.debug("Restoring '%s' from %.2f to %.2f", entity_id, current, player.original_volume)
            actions.append(VolumeAction(entity_id, player.original_volume))
        else:
            _LOGGER.debug("Not restoring '%s': volume is %s, expected %.2f", entity_id, current, player.ducked_volume)
    return DuckPlan(actions=tuple(actions), ducked=remaining)


def ducked_to_data(ducked: Mapping[str, DuckedPlayer]) -> list[dict[str, Any]]:
    """The lowered players as plain data for storage."""
    return [
        {"entity_id": p.entity_id, "original_volume": p.original_volume, "ducked_volume": p.ducked_volume, "areas": sorted(p.areas)}
        for p in ducked.values()
    ]


def ducked_from_data(data: list[dict[str, Any]]) -> dict[str, DuckedPlayer]:
    """The lowered players from what ducked_to_data stored."""
    return {
        item["entity_id"]: DuckedPlayer(item["entity_id"], item["original_volume"], item["ducked_volume"], frozenset(item["areas"]))
        for item in data
    }


def _groups(players: Collection[PlayerSnapshot]) -> list[tuple[PlayerSnapshot, ...]]:
    """The players split into groups: players that list each other as members belong together."""
    by_id = {player.entity_id: player for player in players}
    parent = {entity_id: entity_id for entity_id in by_id}

    def find(entity_id: str) -> str:
        while parent[entity_id] != entity_id:
            parent[entity_id] = parent[parent[entity_id]]
            entity_id = parent[entity_id]
        return entity_id

    for player in players:
        for member in player.group_members:
            if member in by_id:
                parent[find(member)] = find(player.entity_id)

    grouped: dict[str, list[PlayerSnapshot]] = {}
    for entity_id in sorted(by_id):
        grouped.setdefault(find(entity_id), []).append(by_id[entity_id])
    return [tuple(group) for group in grouped.values()]


def _is_group_player(player: PlayerSnapshot) -> bool:
    """A player that lists members but is none of them: it only represents the group."""
    return bool(player.group_members) and player.entity_id not in player.group_members


def _select_target(
    group: tuple[PlayerSnapshot, ...], area_id: str, excluded_entities: Collection[str], excluded_devices: Collection[str]
) -> PlayerSnapshot | None:
    """The one player of a group to lower: a playing one in the area, or None if the group is not playing there."""
    candidates = [
        player
        for player in group
        if player.playing
        and player.can_set_volume
        and not _is_group_player(player)
        and player.entity_id not in excluded_entities
        and (player.device_id is None or player.device_id not in excluded_devices)
    ]
    in_area = [player for player in candidates if player.area_id == area_id]
    return in_area[0] if in_area else None


def _spans_other_areas(group: tuple[PlayerSnapshot, ...], area_id: str) -> bool:
    return any(player.area_id not in (None, area_id) for player in group if not _is_group_player(player))


def _is_ducked(group: tuple[PlayerSnapshot, ...], ducked: Mapping[str, DuckedPlayer]) -> bool:
    return any(player.entity_id in ducked for player in group)


def _keep_ducked(group: tuple[PlayerSnapshot, ...], ducked: dict[str, DuckedPlayer], area_id: str) -> dict[str, DuckedPlayer]:
    """Add the area to the owners of an already lowered group, when the area plays there."""
    updated = dict(ducked)
    if not any(player.playing and player.area_id == area_id for player in group):
        return updated
    for player in group:
        if player.entity_id in updated:
            current = updated[player.entity_id]
            updated[player.entity_id] = DuckedPlayer(current.entity_id, current.original_volume, current.ducked_volume, current.areas | {area_id})
    return updated
