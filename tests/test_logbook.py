"""Tests for the logbook messages."""

import pytest

from custom_components.duck_my_music.ducking import ActionKind, PlayerAction
from custom_components.duck_my_music.logbook import describe_action


@pytest.mark.parametrize(
    ("action", "message"),
    [
        (PlayerAction("media_player.a", ActionKind.VOLUME, 0.3, 0.6), "volume lowered by Duck My Music from 60 % to 30 % because a satellite in the room is busy"),
        (PlayerAction("media_player.a", ActionKind.VOLUME, 0.6, 0.3), "volume restored by Duck My Music from 30 % to 60 %"),
        (PlayerAction("media_player.a", ActionKind.VOLUME, 0.6), "volume set to 60 % by Duck My Music"),
        (PlayerAction("media_player.a", ActionKind.PAUSE), "paused by Duck My Music because a satellite in the room is busy"),
        (PlayerAction("media_player.a", ActionKind.RESUME), "resumed by Duck My Music"),
    ],
)
def test_message_says_what_was_done(action: PlayerAction, message: str) -> None:
    assert describe_action(action) == message
