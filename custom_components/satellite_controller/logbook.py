"""The text of the logbook entries that show on a player's activity what the integration did."""

from __future__ import annotations

from .ducking import ActionKind, PlayerAction

LOGBOOK_NAME = "Satellite Controller"


def describe_action(action: PlayerAction) -> str:
    """
    The message of the logbook entry for an action. It names the integration itself, because
    Home Assistant shows the name of the player as the subject of an entry that has an entity.
    :param action: The action that was applied to a player.
    """
    if action.kind is ActionKind.PAUSE:
        return f"paused by {LOGBOOK_NAME} because a satellite in the room is busy"
    if action.kind is ActionKind.RESUME:
        return f"resumed by {LOGBOOK_NAME}"
    assert action.volume is not None
    if action.previous_volume is not None and action.volume > action.previous_volume:
        return f"volume restored by {LOGBOOK_NAME} from {_percent(action.previous_volume)} to {_percent(action.volume)}"
    if action.previous_volume is not None:
        return f"volume lowered by {LOGBOOK_NAME} from {_percent(action.previous_volume)} to {_percent(action.volume)} because a satellite in the room is busy"
    return f"volume set to {_percent(action.volume)} by {LOGBOOK_NAME}"


def _percent(volume: float) -> str:
    return f"{volume * 100:.0f} %"
