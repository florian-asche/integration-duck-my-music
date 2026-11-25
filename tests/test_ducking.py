"""Tests for planning how to lower and restore the players."""

import logging

import pytest

from custom_components.satellite_controller.ducking import (
    ActionKind,
    CurrentPlayer,
    DuckedPlayer,
    PlayerAction,
    PlayerSnapshot,
    ducked_from_data,
    ducked_to_data,
    plan_duck,
    plan_release,
)


def player(entity_id: str, volume: float | None = 0.6, area_id: str | None = "kitchen", **kwargs) -> PlayerSnapshot:
    values = {"device_id": None, "playing": True, "can_set_volume": True, "can_pause": True, "group_members": ()}
    values.update(kwargs)
    return PlayerSnapshot(entity_id=entity_id, area_id=area_id, volume=volume, **values)


def duck(players, ducked=None, area_id="kitchen", skip_multi_room_groups=False, excluded_entities=(), excluded_devices=(), mode="duck"):
    return plan_duck(players, area_id, 0.5, set(excluded_entities), set(excluded_devices), ducked or {}, skip_multi_room_groups, mode)


def lowered(entity_id: str, volume: float, previous: float) -> PlayerAction:
    return PlayerAction(entity_id, ActionKind.VOLUME, volume, previous)


def current(volume: float | None, state: str = "playing") -> CurrentPlayer:
    return CurrentPlayer(state, volume)


def test_playing_player_is_lowered_by_half_of_its_own_volume() -> None:
    plan = duck([player("media_player.a", 0.6), player("media_player.b", 0.4)])
    assert plan.actions == (lowered("media_player.a", 0.3, 0.6), lowered("media_player.b", 0.2, 0.4))
    assert plan.ducked["media_player.a"] == DuckedPlayer("media_player.a", 0.6, 0.3, frozenset({"kitchen"}))


@pytest.mark.parametrize(
    "other",
    [
        {"playing": False},
        {"can_set_volume": False},
        {"volume": None},
        {"volume": 0.0},
        {"area_id": "bedroom"},
        {"area_id": None},
    ],
)
def test_players_that_cannot_or_need_not_be_lowered_are_left_alone(other) -> None:
    assert duck([player("media_player.a", **other)]).actions == ()


def test_excluded_player_and_device_are_left_alone() -> None:
    players = [player("media_player.a"), player("media_player.b", device_id="satellite-device")]
    plan = duck(players, excluded_entities=["media_player.a"], excluded_devices=["satellite-device"])
    assert plan.actions == ()


def test_group_is_lowered_once_through_one_member() -> None:
    members = ("media_player.a", "media_player.b")
    plan = duck([player("media_player.b", group_members=members), player("media_player.a", group_members=members)])
    assert plan.actions == (lowered("media_player.a", 0.3, 0.6),)
    assert list(plan.ducked) == ["media_player.a"]


def test_group_player_is_never_the_target() -> None:
    group = player("media_player.group", 0.9, group_members=("media_player.a", "media_player.b"))
    plan = duck([group, player("media_player.a", group_members=("media_player.a", "media_player.b")), player("media_player.b")])
    assert [action.entity_id for action in plan.actions] == ["media_player.a"]


def test_group_is_lowered_through_a_member_in_the_area() -> None:
    members = ("media_player.a", "media_player.b")
    plan = duck(
        [
            player("media_player.a", area_id="bedroom", group_members=members),
            player("media_player.b", area_id="kitchen", group_members=members),
        ]
    )
    assert [action.entity_id for action in plan.actions] == ["media_player.b"]


def test_group_without_a_playing_member_in_the_area_is_left_alone() -> None:
    members = ("media_player.a", "media_player.b")
    plan = duck(
        [
            player("media_player.a", area_id="kitchen", playing=False, group_members=members),
            player("media_player.b", area_id="bedroom", group_members=members),
        ]
    )
    assert plan.actions == ()


def test_group_over_several_rooms_can_be_skipped(caplog: pytest.LogCaptureFixture) -> None:
    members = ("media_player.a", "media_player.b")
    players = [player("media_player.a", group_members=members), player("media_player.b", area_id="bedroom", group_members=members)]
    with caplog.at_level(logging.DEBUG):
        assert duck(players, skip_multi_room_groups=True).actions == ()
    assert "has members outside area 'kitchen'" in caplog.text
    assert len(duck(players, skip_multi_room_groups=False).actions) == 1


def test_planning_again_changes_nothing() -> None:
    players = [player("media_player.a")]
    first = duck(players)
    second = duck(players, ducked=first.ducked)
    assert second.actions == ()
    assert second.ducked == first.ducked


def test_second_area_shares_an_already_lowered_group() -> None:
    members = ("media_player.a", "media_player.b")
    players = [
        player("media_player.a", 0.3, area_id="kitchen", group_members=members),
        player("media_player.b", 0.3, area_id="bedroom", group_members=members),
    ]
    first = duck([player("media_player.a", 0.6, group_members=members), player("media_player.b", 0.6, area_id="bedroom", group_members=members)])
    second = duck(players, ducked=first.ducked, area_id="bedroom")
    assert second.actions == ()
    assert second.ducked["media_player.a"].areas == {"kitchen", "bedroom"}


def test_release_restores_the_original_volume() -> None:
    ducked = duck([player("media_player.a", 0.6)]).ducked
    plan = plan_release("kitchen", ducked, {"media_player.a": current(0.3)})
    assert plan.actions == (PlayerAction("media_player.a", ActionKind.VOLUME, 0.6, 0.3),)
    assert plan.ducked == {}


def test_release_does_not_restore_a_volume_changed_meanwhile(caplog: pytest.LogCaptureFixture) -> None:
    ducked = duck([player("media_player.a", 0.6)]).ducked
    with caplog.at_level(logging.INFO):
        plan = plan_release("kitchen", ducked, {"media_player.a": current(0.8)})
    assert plan.actions == ()
    assert plan.ducked == {}
    assert [(record.levelno, record.getMessage()) for record in caplog.records if record.levelno >= logging.INFO] == [
        (
            logging.INFO,
            "Not restoring the volume of 'media_player.a': Satellite Controller lowered it to 0.3, but it is now 0.8, so it was changed by someone else",
        )
    ]


def test_release_skips_players_that_are_gone() -> None:
    ducked = duck([player("media_player.a", 0.6)]).ducked
    assert plan_release("kitchen", ducked, {"media_player.a": current(None, "unavailable")}).actions == ()


def test_release_keeps_a_player_another_area_still_needs() -> None:
    ducked = {"media_player.a": DuckedPlayer("media_player.a", 0.6, 0.3, frozenset({"kitchen", "bedroom"}))}
    plan = plan_release("kitchen", ducked, {"media_player.a": current(0.3)})
    assert plan.actions == ()
    assert plan.ducked["media_player.a"].areas == {"bedroom"}


def test_release_of_all_areas() -> None:
    ducked = {"media_player.a": DuckedPlayer("media_player.a", 0.6, 0.3, frozenset({"kitchen", "bedroom"}))}
    plan = plan_release(None, ducked, {"media_player.a": current(0.3)})
    assert plan.actions == (PlayerAction("media_player.a", ActionKind.VOLUME, 0.6, 0.3),)


def test_ducked_players_survive_storage() -> None:
    ducked = {"media_player.a": DuckedPlayer("media_player.a", 0.6, 0.3, frozenset({"kitchen", "bedroom"}))}
    assert ducked_from_data(ducked_to_data(ducked)) == ducked


@pytest.mark.parametrize(
    ("other", "excluded", "reason"),
    [
        ({"playing": False}, {}, "it is not playing"),
        ({"can_pause": False}, {"mode": "pause"}, "it does not support pause"),
        ({"can_set_volume": False}, {}, "it does not support setting the volume"),
        ({"area_id": "bedroom"}, {}, "it is in area 'bedroom', not 'kitchen'"),
        ({"device_id": "sat"}, {"excluded_devices": ["sat"]}, "it belongs to the busy satellite's own device"),
        ({}, {"excluded_entities": ["media_player.a"]}, "it is excluded in the options"),
        ({"group_members": ("media_player.b",)}, {}, "it only represents a group"),
    ],
)
def test_the_reason_a_player_is_not_lowered_is_logged(caplog: pytest.LogCaptureFixture, other, excluded, reason) -> None:
    with caplog.at_level(logging.DEBUG):
        duck([player("media_player.a", **other)], **excluded)
    assert f"Player 'media_player.a' not lowered: {reason}" in caplog.text
    assert "nothing to lower in area 'kitchen'" in caplog.text


def test_pause_mode_pauses_instead_of_lowering() -> None:
    plan = duck([player("media_player.a", 0.6)], mode="pause")
    assert plan.actions == (PlayerAction("media_player.a", ActionKind.PAUSE),)
    assert plan.ducked["media_player.a"] == DuckedPlayer("media_player.a", None, None, frozenset({"kitchen"}), paused=True)


def test_pause_mode_needs_pause_support_but_not_volume_control() -> None:
    assert duck([player("media_player.a", can_pause=False)], mode="pause").actions == ()
    assert duck([player("media_player.a", None, can_set_volume=False)], mode="pause").actions == (PlayerAction("media_player.a", ActionKind.PAUSE),)


def test_pause_mode_pauses_a_group_once() -> None:
    members = ("media_player.a", "media_player.b")
    plan = duck([player("media_player.a", group_members=members), player("media_player.b", group_members=members)], mode="pause")
    assert plan.actions == (PlayerAction("media_player.a", ActionKind.PAUSE),)


def test_release_resumes_a_paused_player() -> None:
    ducked = duck([player("media_player.a")], mode="pause").ducked
    plan = plan_release("kitchen", ducked, {"media_player.a": current(0.6, "paused")})
    assert plan.actions == (PlayerAction("media_player.a", ActionKind.RESUME),)
    assert plan.ducked == {}


@pytest.mark.parametrize("state", ["playing", "idle", "off", "unavailable"])
def test_release_does_not_resume_a_player_that_is_not_paused_any_more(caplog: pytest.LogCaptureFixture, state: str) -> None:
    ducked = duck([player("media_player.a")], mode="pause").ducked
    with caplog.at_level(logging.INFO):
        plan = plan_release("kitchen", ducked, {"media_player.a": current(0.6, state)})
    assert plan.actions == ()
    assert [record.levelno for record in caplog.records if record.levelno >= logging.INFO] == [logging.INFO]
    assert f"Not resuming 'media_player.a': it was paused by Satellite Controller, but its state is now {state}" in caplog.text


def test_paused_players_survive_storage_and_old_data_is_not_paused() -> None:
    ducked = {"media_player.a": DuckedPlayer("media_player.a", None, None, frozenset({"kitchen"}), paused=True)}
    assert ducked_from_data(ducked_to_data(ducked)) == ducked
    old = [{"entity_id": "media_player.a", "original_volume": 0.6, "ducked_volume": 0.3, "areas": ["kitchen"]}]
    assert ducked_from_data(old)["media_player.a"].paused is False
