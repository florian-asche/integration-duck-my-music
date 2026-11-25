"""Tests for the logbook messages."""

import pytest

from custom_components.satellite_controller.ducking import ActionKind, PlayerAction
from custom_components.satellite_controller.logbook import describe_action


@pytest.mark.parametrize(
    ("action", "message"),
    [
        (PlayerAction("media_player.a", ActionKind.VOLUME, 0.3, 0.6), "lowered the volume from 60 % to 30 % because a satellite in the room is busy"),
        (PlayerAction("media_player.a", ActionKind.VOLUME, 0.6, 0.3), "restored the volume from 30 % to 60 %"),
        (PlayerAction("media_player.a", ActionKind.VOLUME, 0.6), "set the volume to 60 %"),
        (PlayerAction("media_player.a", ActionKind.PAUSE), "paused the music because a satellite in the room is busy"),
        (PlayerAction("media_player.a", ActionKind.RESUME), "resumed the music"),
    ],
)
def test_message_says_what_was_done(action: PlayerAction, message: str) -> None:
    assert describe_action(action) == message
