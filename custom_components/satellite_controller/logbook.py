"""The text of the logbook entries that show on a player's activity what the integration did."""

from __future__ import annotations

from .ducking import ActionKind, PlayerAction

LOGBOOK_NAME = "Satellite Controller"


def describe_action(action: PlayerAction) -> str:
    """
    The message of the logbook entry for an action, shown after the name ``Satellite Controller``.
    :param action: The action that was applied to a player.
    """
    if action.kind is ActionKind.PAUSE:
        return "paused the music because a satellite in the room is busy"
    if action.kind is ActionKind.RESUME:
        return "resumed the music"
    assert action.volume is not None
    if action.previous_volume is not None and action.volume > action.previous_volume:
        return f"restored the volume from {_percent(action.previous_volume)} to {_percent(action.volume)}"
    if action.previous_volume is not None:
        return f"lowered the volume from {_percent(action.previous_volume)} to {_percent(action.volume)} because a satellite in the room is busy"
    return f"set the volume to {_percent(action.volume)}"


def _percent(volume: float) -> str:
    return f"{volume * 100:.0f} %"
