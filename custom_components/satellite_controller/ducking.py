"""Plans how to lower and restore the music of the players in a room.

Everything here is a pure function over snapshots of the players: no Home
Assistant access, no service calls. The controller reads the snapshots, calls
these functions and applies the returned actions.

Players that are in the same group are handled as one unit, through a single
device of the group, because changing the volume of one member (or pausing it)
can change the others as well. The music is either lowered or paused.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum
import logging
from typing import Any

from .const import MODE_PAUSE

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
    can_pause: bool = False
    group_members: tuple[str, ...] = ()


@dataclass(frozen=True)
class CurrentPlayer:
    """The state and volume of a player right now."""

    state: str | None
    volume: float | None


class ActionKind(StrEnum):
    """What to do to a player."""

    VOLUME = "volume"
    PAUSE = "pause"
    RESUME = "resume"


@dataclass(frozen=True)
class PlayerAction:
    """Set a player to a volume (0..1), pause it or resume it. ``previous_volume`` is what it had before a volume change."""

    entity_id: str
    kind: ActionKind
    volume: float | None = None
    previous_volume: float | None = None


@dataclass(frozen=True)
class DuckedPlayer:
    """A player that was lowered or paused, and the areas that are keeping it that way."""

    entity_id: str
    original_volume: float | None
    ducked_volume: float | None
    areas: frozenset[str]
    paused: bool = False


@dataclass(frozen=True)
class DuckPlan:
    """The volume changes to apply and the lowered players afterwards."""

    actions: tuple[PlayerAction, ...]
    ducked: Mapping[str, DuckedPlayer]


def plan_duck(
    players: Collection[PlayerSnapshot],
    area_id: str,
    duck_fraction: float,
    excluded_entities: Collection[str],
    excluded_devices: Collection[str],
    ducked: Mapping[str, DuckedPlayer],
    skip_multi_room_groups: bool,
    mode: str,
) -> DuckPlan:
    """
    Plan lowering or pausing the music in an area.
    :param players: Snapshots of all players that may be lowered, in any area.
    :param area_id: The area whose satellite became busy.
    :param duck_fraction: How much of its own volume each player loses (0.5 halves it).
    :param excluded_entities: Players that are never lowered.
    :param excluded_devices: Devices whose players are never lowered, such as the busy satellite itself.
    :param ducked: The players that are lowered already.
    :param skip_multi_room_groups: Leave groups alone that have members in other areas.
    :param mode: ``"duck"`` lowers the volume, ``"pause"`` pauses the player.
    :return: The volume changes to apply and the lowered players afterwards. Calling it again with the
        result as ``ducked`` changes nothing.
    """
    result = dict(ducked)
    actions: list[PlayerAction] = []
    groups = _groups(players)
    _LOGGER.debug("Planning area '%s': %d players in %d groups, mode %s, %.0f %% reduction", area_id, len(players), len(groups), mode, duck_fraction * 100)
    for group in groups:
        names = ", ".join(player.entity_id for player in group)
        if _is_ducked(group, result):
            _LOGGER.debug("Group [%s] is lowered already, area '%s' now keeps it lowered too", names, area_id)
            result = _keep_ducked(group, result, area_id)
            continue
        target = _select_target(group, area_id, excluded_entities, excluded_devices, mode)
        if target is None:
            _LOGGER.debug("Group [%s]: nothing to lower in area '%s'", names, area_id)
            continue
        if mode != MODE_PAUSE and (target.volume is None or target.volume <= 0):
            _LOGGER.debug("Group [%s]: '%s' has volume %s, nothing to lower", names, target.entity_id, target.volume)
            continue
        if skip_multi_room_groups and _spans_other_areas(group, area_id):
            _LOGGER.debug("Group of '%s' has members outside area '%s', skipped", target.entity_id, area_id)
            continue
        if mode == MODE_PAUSE:
            _LOGGER.debug("Pausing '%s' in area '%s'", target.entity_id, area_id)
            actions.append(PlayerAction(target.entity_id, ActionKind.PAUSE))
            result[target.entity_id] = DuckedPlayer(target.entity_id, None, None, frozenset({area_id}), paused=True)
            continue
        assert target.volume is not None
        ducked_volume = round(target.volume * (1 - duck_fraction), 4)
        _LOGGER.debug("Lowering '%s' in area '%s' from %.2f to %.2f", target.entity_id, area_id, target.volume, ducked_volume)
        actions.append(PlayerAction(target.entity_id, ActionKind.VOLUME, ducked_volume, target.volume))
        result[target.entity_id] = DuckedPlayer(target.entity_id, target.volume, ducked_volume, frozenset({area_id}))
    return DuckPlan(actions=tuple(actions), ducked=result)


def plan_release(area_id: str | None, ducked: Mapping[str, DuckedPlayer], current: Mapping[str, CurrentPlayer]) -> DuckPlan:
    """
    Plan restoring the music of an area, or of all areas.
    :param area_id: The area whose satellite is quiet again, ``None`` for all areas.
    :param ducked: The players that are lowered or paused.
    :param current: The current state and volume of each player.
    :return: The changes to apply and the players that stay lowered or paused. A player that another area
        still keeps that way stays. A player whose volume was changed, or that was resumed or stopped by
        someone else, is left as it is.
    """
    remaining: dict[str, DuckedPlayer] = {}
    actions: list[PlayerAction] = []
    for entity_id, player in ducked.items():
        areas = player.areas - {area_id} if area_id is not None else frozenset()
        if areas:
            remaining[entity_id] = DuckedPlayer(entity_id, player.original_volume, player.ducked_volume, areas, player.paused)
            continue
        now = current.get(entity_id, CurrentPlayer(None, None))
        if player.paused:
            if now.state == "paused":
                _LOGGER.debug("Resuming '%s'", entity_id)
                actions.append(PlayerAction(entity_id, ActionKind.RESUME))
            else:
                _LOGGER.debug("Not resuming '%s': state is %s, expected paused", entity_id, now.state)
        elif player.ducked_volume is not None and player.original_volume is not None and now.volume is not None and abs(now.volume - player.ducked_volume) <= VOLUME_TOLERANCE:
            _LOGGER.debug("Restoring '%s' from %.2f to %.2f", entity_id, now.volume, player.original_volume)
            actions.append(PlayerAction(entity_id, ActionKind.VOLUME, player.original_volume, now.volume))
        else:
            _LOGGER.debug("Not restoring '%s': volume is %s, expected %s", entity_id, now.volume, player.ducked_volume)
    return DuckPlan(actions=tuple(actions), ducked=remaining)


def ducked_to_data(ducked: Mapping[str, DuckedPlayer]) -> list[dict[str, Any]]:
    """The lowered players as plain data for storage."""
    return [
        {"entity_id": p.entity_id, "original_volume": p.original_volume, "ducked_volume": p.ducked_volume, "areas": sorted(p.areas), "paused": p.paused}
        for p in ducked.values()
    ]


def ducked_from_data(data: list[dict[str, Any]]) -> dict[str, DuckedPlayer]:
    """The lowered players from what ducked_to_data stored."""
    return {
        item["entity_id"]: DuckedPlayer(item["entity_id"], item["original_volume"], item["ducked_volume"], frozenset(item["areas"]), item.get("paused", False))
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
    group: tuple[PlayerSnapshot, ...], area_id: str, excluded_entities: Collection[str], excluded_devices: Collection[str], mode: str
) -> PlayerSnapshot | None:
    """The one player of a group to lower or pause: a playing one in the area, or None if the group is not playing there."""
    in_area = []
    for player in group:
        reason = _rejection_reason(player, area_id, excluded_entities, excluded_devices, mode)
        if reason is None:
            in_area.append(player)
        else:
            _LOGGER.debug("Player '%s' not lowered: %s", player.entity_id, reason)
    return in_area[0] if in_area else None


def _rejection_reason(player: PlayerSnapshot, area_id: str, excluded_entities: Collection[str], excluded_devices: Collection[str], mode: str) -> str | None:
    """Why a player is not lowered for an area, or None if it is a candidate."""
    if player.area_id != area_id:
        return f"it is in area '{player.area_id}', not '{area_id}'"
    if player.entity_id in excluded_entities:
        return "it is excluded in the options"
    if player.device_id is not None and player.device_id in excluded_devices:
        return "it belongs to the busy satellite's own device"
    if _is_group_player(player):
        return "it only represents a group (lists members but is none of them)"
    if not player.playing:
        return "it is not playing"
    if mode == MODE_PAUSE and not player.can_pause:
        return "it does not support pause"
    if mode != MODE_PAUSE and not player.can_set_volume:
        return "it does not support setting the volume"
    return None


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
            updated[player.entity_id] = DuckedPlayer(current.entity_id, current.original_volume, current.ducked_volume, current.areas | {area_id}, current.paused)
    return updated
