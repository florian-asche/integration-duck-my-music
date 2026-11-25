"""Plans how to lower and restore the music of the players in a room.

Everything here is a pure function over snapshots of the players: no Home
Assistant access, no service calls. The controller reads the snapshots, calls
these functions and applies the returned actions.

The volumes of all players are read in one step, and every target is computed
from that snapshot, never from a volume that an earlier change may have moved
(players can be synchronized without this integration knowing). A sync group
player is handled instead of its members. The music is either lowered or paused.
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
    expected_volume: float | None = None


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
    mode: str,
) -> DuckPlan:
    """
    Plan lowering or pausing the music in an area.
    :param players: Snapshots of all players that may be lowered, in any area, read in one step.
    :param area_id: The area whose satellite became busy.
    :param duck_fraction: How much of its own volume each player loses (0.5 halves it).
    :param excluded_entities: Players that are never lowered.
    :param excluded_devices: Devices whose players are never lowered, such as the busy satellite itself.
    :param ducked: The players that are lowered already.
    :param mode: ``"duck"`` lowers the volume, ``"pause"`` pauses the player.
    :return: The changes to apply and the lowered players afterwards. A group player that is playing in the area is
        handled instead of its members, every other player on its own, with a target computed from its own
        snapshot volume. Calling it again with the result as ``ducked`` changes nothing.
    """
    result = dict(ducked)
    actions: list[PlayerAction] = []
    _LOGGER.debug("Planning area '%s': %d players, mode %s, %.0f %% reduction", area_id, len(players), mode, duck_fraction * 100)
    by_id = {player.entity_id: player for player in players}
    covered: dict[str, str] = {}
    for group in sorted((player for player in players if _is_group_player(player)), key=lambda candidate: candidate.entity_id):
        members = tuple(by_id[member] for member in group.group_members if member in by_id)
        reason = _group_rejection_reason(group, members, area_id, excluded_entities, excluded_devices, mode)
        if reason is not None:
            _LOGGER.debug("Group player '%s' not lowered: %s", group.entity_id, reason)
            continue
        covered.update({member.entity_id: group.entity_id for member in members})
        if group.entity_id in result:
            _LOGGER.debug("Group player '%s' is lowered already", group.entity_id)
            continue
        action = _plan_group(group, members, area_id, duck_fraction, mode, result)
        if action is not None:
            actions.append(action)
    for player in sorted(players, key=lambda candidate: candidate.entity_id):
        if _is_group_player(player):
            continue
        if player.entity_id in covered:
            _LOGGER.debug("Player '%s' not lowered on its own: its group player '%s' is lowered instead", player.entity_id, covered[player.entity_id])
            continue
        reason = _rejection_reason(player, area_id, excluded_entities, excluded_devices, mode)
        if reason is not None:
            _LOGGER.debug("Player '%s' not lowered: %s", player.entity_id, reason)
            continue
        if player.entity_id in result:
            _LOGGER.debug("Player '%s' is lowered already", player.entity_id)
            continue
        if mode == MODE_PAUSE:
            _LOGGER.debug("Pausing '%s' in area '%s'", player.entity_id, area_id)
            actions.append(PlayerAction(player.entity_id, ActionKind.PAUSE))
            result[player.entity_id] = DuckedPlayer(player.entity_id, None, None, frozenset({area_id}), paused=True)
            continue
        if player.volume is None or player.volume <= 0:
            _LOGGER.debug("Player '%s' has volume %s, nothing to lower", player.entity_id, player.volume)
            continue
        ducked_volume = round(player.volume * (1 - duck_fraction), 4)
        _LOGGER.debug("Lowering '%s' in area '%s' from %.2f to %.2f", player.entity_id, area_id, player.volume, ducked_volume)
        actions.append(PlayerAction(player.entity_id, ActionKind.VOLUME, ducked_volume, player.volume))
        result[player.entity_id] = DuckedPlayer(player.entity_id, player.volume, ducked_volume, frozenset({area_id}))
    return DuckPlan(actions=tuple(actions), ducked=result)


def plan_release(area_id: str | None, ducked: Mapping[str, DuckedPlayer], current: Mapping[str, CurrentPlayer]) -> DuckPlan:
    """
    Plan restoring the music of an area, or of all areas.
    :param area_id: The area whose satellite is quiet again, ``None`` for all areas.
    :param ducked: The players that are lowered or paused.
    :param current: The current state and volume of each player.
    :return: The changes to apply and the players that stay lowered or paused. A player that another area
        still keeps that way stays. A player whose volume is none of the lowered volumes (changed by someone
        else), or that was resumed or stopped by someone else, is left as it is. Any of the lowered volumes
        counts, because synchronized players can end up at the volume of another player.
    """
    remaining: dict[str, DuckedPlayer] = {}
    actions: list[PlayerAction] = []
    lowered_volumes = [
        player.expected_volume if player.expected_volume is not None else player.ducked_volume
        for player in ducked.values()
        if player.expected_volume is not None or player.ducked_volume is not None
    ]
    for entity_id, player in ducked.items():
        areas = player.areas - {area_id} if area_id is not None else frozenset()
        if areas:
            remaining[entity_id] = DuckedPlayer(entity_id, player.original_volume, player.ducked_volume, areas, player.paused, player.expected_volume)
            continue
        now = current.get(entity_id, CurrentPlayer(None, None))
        if player.paused:
            if now.state == "paused":
                _LOGGER.debug("Resuming '%s'", entity_id)
                actions.append(PlayerAction(entity_id, ActionKind.RESUME))
            else:
                _LOGGER.info("Not resuming '%s': it was paused by Satellite Controller, but its state is now %s, so it was changed by someone else", entity_id, now.state)
        elif player.original_volume is not None and now.volume is not None and _is_lowered_volume(now.volume, lowered_volumes):
            _LOGGER.debug("Restoring '%s' from %.2f to %.2f", entity_id, now.volume, player.original_volume)
            actions.append(PlayerAction(entity_id, ActionKind.VOLUME, player.original_volume, now.volume))
        else:
            _LOGGER.info(
                "Not restoring the volume of '%s': Satellite Controller lowered it to %s, but it is now %s, so it was changed by someone else",
                entity_id,
                player.ducked_volume,
                now.volume,
            )
    return DuckPlan(actions=tuple(actions), ducked=remaining)


def ducked_to_data(ducked: Mapping[str, DuckedPlayer]) -> list[dict[str, Any]]:
    """The lowered players as plain data for storage."""
    return [
        {
            "entity_id": p.entity_id,
            "original_volume": p.original_volume,
            "ducked_volume": p.ducked_volume,
            "areas": sorted(p.areas),
            "paused": p.paused,
            "expected_volume": p.expected_volume,
        }
        for p in ducked.values()
    ]


def ducked_from_data(data: list[dict[str, Any]]) -> dict[str, DuckedPlayer]:
    """The lowered players from what ducked_to_data stored."""
    return {
        item["entity_id"]: DuckedPlayer(item["entity_id"], item["original_volume"], item["ducked_volume"], frozenset(item["areas"]), item.get("paused", False), item.get("expected_volume"))
        for item in data
    }


def _plan_group(
    group: PlayerSnapshot, members: tuple[PlayerSnapshot, ...], area_id: str, duck_fraction: float, mode: str, result: dict[str, DuckedPlayer]
) -> PlayerAction | None:
    """
    Plan a sync group player: it is set, and its members are not.

    Music Assistant scales the members in proportion to the highest of them, so the highest member volume is
    the volume to lower and to restore. The volume the group player reports (the average of its members) is
    what to expect after lowering.
    """
    if mode == MODE_PAUSE:
        _LOGGER.debug("Pausing group player '%s' in area '%s'", group.entity_id, area_id)
        result[group.entity_id] = DuckedPlayer(group.entity_id, None, None, frozenset({area_id}), paused=True)
        return PlayerAction(group.entity_id, ActionKind.PAUSE)
    levels = [member.volume for member in members if member.volume is not None]
    base = max(levels) if levels else group.volume
    if base is None or base <= 0:
        _LOGGER.debug("Group player '%s' has volume %s, nothing to lower", group.entity_id, base)
        return None
    ducked_volume = round(base * (1 - duck_fraction), 4)
    expected = round(group.volume * (1 - duck_fraction), 4) if group.volume is not None else ducked_volume
    _LOGGER.debug("Lowering group player '%s' in area '%s' from %.2f to %.2f (it reports %s)", group.entity_id, area_id, base, ducked_volume, group.volume)
    result[group.entity_id] = DuckedPlayer(group.entity_id, base, ducked_volume, frozenset({area_id}), expected_volume=expected)
    return PlayerAction(group.entity_id, ActionKind.VOLUME, ducked_volume, base)


def _group_rejection_reason(
    group: PlayerSnapshot,
    members: tuple[PlayerSnapshot, ...],
    area_id: str,
    excluded_entities: Collection[str],
    excluded_devices: Collection[str],
    mode: str,
) -> str | None:
    """Why a group player is not lowered for an area, or None if it is."""
    if group.entity_id in excluded_entities:
        return "it is excluded in the options"
    if group.device_id is not None and group.device_id in excluded_devices:
        return "it belongs to the busy satellite's own device"
    for member in members:
        if member.entity_id in excluded_entities:
            return f"its member '{member.entity_id}' is excluded in the options, so the members are handled on their own"
        if member.device_id is not None and member.device_id in excluded_devices:
            return f"its member '{member.entity_id}' belongs to the busy satellite's own device, so the members are handled on their own"
    if group.area_id != area_id and not any(member.area_id == area_id for member in members):
        return f"neither it nor its members are in area '{area_id}'"
    if not group.playing:
        return "it is not playing"
    if mode == MODE_PAUSE and not group.can_pause:
        return "it does not support pause"
    if mode != MODE_PAUSE and not group.can_set_volume:
        return "it does not support setting the volume"
    return None


def _is_group_player(player: PlayerSnapshot) -> bool:
    """A player that lists members but is none of them: it only represents the group."""
    return bool(player.group_members) and player.entity_id not in player.group_members


def _rejection_reason(player: PlayerSnapshot, area_id: str, excluded_entities: Collection[str], excluded_devices: Collection[str], mode: str) -> str | None:
    """Why a player is not lowered for an area, or None if it is a candidate."""
    if player.area_id != area_id:
        return f"it is in area '{player.area_id}', not '{area_id}'"
    if player.entity_id in excluded_entities:
        return "it is excluded in the options"
    if player.device_id is not None and player.device_id in excluded_devices:
        return "it belongs to the busy satellite's own device"
    if not player.playing:
        return "it is not playing"
    if mode == MODE_PAUSE and not player.can_pause:
        return "it does not support pause"
    if mode != MODE_PAUSE and not player.can_set_volume:
        return "it does not support setting the volume"
    return None


def _is_lowered_volume(volume: float, lowered_volumes: Collection[float]) -> bool:
    return any(abs(volume - lowered) <= VOLUME_TOLERANCE for lowered in lowered_volumes)
