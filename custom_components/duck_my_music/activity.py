"""Which voice satellites are busy in which area.

A satellite is busy from its first state after ``idle`` until it is ``idle``
again. The functions here only track that; lowering the music is decided
elsewhere (ducking.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

ACTIVE_SATELLITE_STATES = frozenset({"listening", "processing", "responding"})


@dataclass(frozen=True)
class ActivityChange:
    """The busy satellites per area after a state change, and which areas just became busy or quiet."""

    active: Mapping[str, frozenset[str]]
    started_areas: frozenset[str]
    ended_areas: frozenset[str]


def update_activity(active: Mapping[str, frozenset[str]], satellite_id: str, area_id: str | None, state: str) -> ActivityChange:
    """
    Apply one state change of a satellite to the busy satellites.
    :param active: Busy satellite entity ids per area before the change.
    :param satellite_id: Entity id of the satellite that changed.
    :param area_id: Effective area of the satellite, ``None`` if it has none.
    :param state: New state of the satellite entity.
    :return: The busy satellites after the change and the areas that became busy or quiet.
    """
    busy = state in ACTIVE_SATELLITE_STATES and area_id is not None
    updated: dict[str, frozenset[str]] = {}
    for area, satellites in active.items():
        remaining = satellites - {satellite_id}
        if remaining:
            updated[area] = remaining
    if busy and area_id is not None:
        updated[area_id] = updated.get(area_id, frozenset()) | {satellite_id}

    started = frozenset(area for area in updated if area not in active)
    ended = frozenset(area for area in active if area not in updated)
    return ActivityChange(active=updated, started_areas=started, ended_areas=ended)
