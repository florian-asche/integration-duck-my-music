"""Tests for the logbook messages."""

import pytest

from custom_components.satellite_controller.ducking import ActionKind, PlayerAction
from custom_components.satellite_controller.logbook import describe_action


@pytest.mark.parametrize(
    ("action", "message"),
    [
        (PlayerAction("media_player.a", ActionKind.VOLUME, 0.3, 0.6), "volume lowered by Satellite Controller from 60 % to 30 % because a satellite in the room is busy"),
        (PlayerAction("media_player.a", ActionKind.VOLUME, 0.6, 0.3), "volume restored by Satellite Controller from 30 % to 60 %"),
        (PlayerAction("media_player.a", ActionKind.VOLUME, 0.6), "volume set to 60 % by Satellite Controller"),
        (PlayerAction("media_player.a", ActionKind.PAUSE), "paused by Satellite Controller because a satellite in the room is busy"),
        (PlayerAction("media_player.a", ActionKind.RESUME), "resumed by Satellite Controller"),
    ],
)
def test_message_says_what_was_done(action: PlayerAction, message: str) -> None:
    assert describe_action(action) == message
