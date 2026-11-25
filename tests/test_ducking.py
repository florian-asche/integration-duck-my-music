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


def duck(players, ducked=None, area_id="kitchen", excluded_entities=(), excluded_devices=(), mode="duck"):
    return plan_duck(players, area_id, 0.5, set(excluded_entities), set(excluded_devices), ducked or {}, mode)


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




def test_planning_again_changes_nothing() -> None:
    players = [player("media_player.a")]
    first = duck(players)
    second = duck(players, ducked=first.ducked)
    assert second.actions == ()
    assert second.ducked == first.ducked



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
    ],
)
def test_the_reason_a_player_is_not_lowered_is_logged(caplog: pytest.LogCaptureFixture, other, excluded, reason) -> None:
    with caplog.at_level(logging.DEBUG):
        duck([player("media_player.a", **other)], **excluded)
    assert f"Player 'media_player.a' not lowered: {reason}" in caplog.text


def test_pause_mode_pauses_instead_of_lowering() -> None:
    plan = duck([player("media_player.a", 0.6)], mode="pause")
    assert plan.actions == (PlayerAction("media_player.a", ActionKind.PAUSE),)
    assert plan.ducked["media_player.a"] == DuckedPlayer("media_player.a", None, None, frozenset({"kitchen"}), paused=True)


def test_pause_mode_needs_pause_support_but_not_volume_control() -> None:
    assert duck([player("media_player.a", can_pause=False)], mode="pause").actions == ()
    assert duck([player("media_player.a", None, can_set_volume=False)], mode="pause").actions == (PlayerAction("media_player.a", ActionKind.PAUSE),)



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


def test_every_player_of_a_group_is_lowered_from_its_own_snapshot() -> None:
    members = ("media_player.a", "media_player.b")
    plan = duck([player("media_player.b", 0.4, group_members=members), player("media_player.a", 0.6, group_members=members)])
    assert plan.actions == (lowered("media_player.a", 0.3, 0.6), lowered("media_player.b", 0.2, 0.4))


def test_pause_mode_pauses_every_playing_player() -> None:
    plan = duck([player("media_player.a"), player("media_player.b")], mode="pause")
    assert plan.actions == (PlayerAction("media_player.a", ActionKind.PAUSE), PlayerAction("media_player.b", ActionKind.PAUSE))


def test_release_restores_players_that_were_synchronized_to_another_lowered_volume() -> None:
    ducked = duck([player("media_player.a", 0.6), player("media_player.b", 0.4)]).ducked
    plan = plan_release("kitchen", ducked, {"media_player.a": current(0.2), "media_player.b": current(0.2)})
    assert plan.actions == (
        PlayerAction("media_player.a", ActionKind.VOLUME, 0.6, 0.2),
        PlayerAction("media_player.b", ActionKind.VOLUME, 0.4, 0.2),
    )


def test_release_does_not_restore_a_volume_that_matches_none_of_the_lowered_volumes() -> None:
    ducked = duck([player("media_player.a", 0.6), player("media_player.b", 0.4)]).ducked
    plan = plan_release("kitchen", ducked, {"media_player.a": current(0.2), "media_player.b": current(0.9)})
    assert plan.actions == (PlayerAction("media_player.a", ActionKind.VOLUME, 0.6, 0.2),)


MEMBERS = ("media_player.a", "media_player.b")


def sync_group(volume: float | None = 0.5, area_id: str | None = None, **kwargs) -> PlayerSnapshot:
    return player("media_player.group", volume, area_id=area_id, group_members=MEMBERS, **kwargs)


def test_sync_group_player_is_lowered_instead_of_its_members() -> None:
    plan = duck([sync_group(0.5), player("media_player.a", 0.6), player("media_player.b", 0.4)])
    assert plan.actions == (lowered("media_player.group", 0.3, 0.6),)
    assert list(plan.ducked) == ["media_player.group"]


def test_sync_group_player_is_lowered_by_the_highest_member_volume_and_expects_half_of_its_own_volume() -> None:
    plan = duck([sync_group(0.5), player("media_player.a", 0.6), player("media_player.b", 0.4)])
    assert plan.ducked["media_player.group"] == DuckedPlayer("media_player.group", 0.6, 0.3, frozenset({"kitchen"}), expected_volume=0.25)


def test_sync_group_player_without_member_volumes_uses_its_own_volume() -> None:
    plan = duck([sync_group(0.5, area_id="kitchen")])
    assert plan.actions == (lowered("media_player.group", 0.25, 0.5),)


def test_sync_group_player_without_an_area_counts_through_a_member_in_the_area() -> None:
    plan = duck([sync_group(area_id=None), player("media_player.a", area_id="kitchen"), player("media_player.b", area_id="bedroom")])
    assert [action.entity_id for action in plan.actions] == ["media_player.group"]


def test_sync_group_player_in_another_area_is_left_alone() -> None:
    plan = duck([sync_group(area_id="bedroom"), player("media_player.a", area_id="bedroom"), player("media_player.b", area_id="bedroom")])
    assert plan.actions == ()


def test_members_are_lowered_on_their_own_while_the_group_player_is_not_playing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        plan = duck([sync_group(playing=False), player("media_player.a", 0.6), player("media_player.b", 0.4)])
    assert [action.entity_id for action in plan.actions] == ["media_player.a", "media_player.b"]
    assert "Group player 'media_player.group' not lowered: it is not playing" in caplog.text


def test_group_player_that_cannot_set_the_volume_leaves_the_members_to_themselves() -> None:
    plan = duck([sync_group(can_set_volume=False), player("media_player.a", 0.6), player("media_player.b", 0.4)])
    assert [action.entity_id for action in plan.actions] == ["media_player.a", "media_player.b"]


def test_group_with_the_satellites_own_player_is_not_lowered_as_a_whole(caplog: pytest.LogCaptureFixture) -> None:
    players = [sync_group(), player("media_player.a", 0.6, device_id="satellite-device"), player("media_player.b", 0.4)]
    with caplog.at_level(logging.DEBUG):
        plan = duck(players, excluded_devices=["satellite-device"])
    assert [action.entity_id for action in plan.actions] == ["media_player.b"]
    assert "its member 'media_player.a' belongs to the busy satellite's own device" in caplog.text


def test_group_with_an_excluded_member_is_not_lowered_as_a_whole() -> None:
    plan = duck([sync_group(), player("media_player.a", 0.6), player("media_player.b", 0.4)], excluded_entities=["media_player.a"])
    assert [action.entity_id for action in plan.actions] == ["media_player.b"]


def test_excluded_group_player_is_not_lowered_and_its_members_are_handled_on_their_own() -> None:
    plan = duck([sync_group(), player("media_player.a", 0.6), player("media_player.b", 0.4)], excluded_entities=["media_player.group"])
    assert [action.entity_id for action in plan.actions] == ["media_player.a", "media_player.b"]


def test_member_of_a_lowered_group_is_not_lowered_when_planning_again(caplog: pytest.LogCaptureFixture) -> None:
    players = [sync_group(), player("media_player.a", 0.6), player("media_player.b", 0.4)]
    first = duck(players)
    with caplog.at_level(logging.DEBUG):
        second = duck(players, ducked=first.ducked)
    assert second.actions == ()
    assert second.ducked == first.ducked
    assert "Player 'media_player.a' not lowered on its own: its group player 'media_player.group' is lowered instead" in caplog.text


def test_pause_mode_pauses_the_group_player_and_not_its_members() -> None:
    plan = duck([sync_group(), player("media_player.a"), player("media_player.b")], mode="pause")
    assert plan.actions == (PlayerAction("media_player.group", ActionKind.PAUSE),)


def test_release_restores_a_group_player_to_the_highest_member_volume() -> None:
    ducked = duck([sync_group(0.5), player("media_player.a", 0.6), player("media_player.b", 0.4)]).ducked
    plan = plan_release("kitchen", ducked, {"media_player.group": current(0.25)})
    assert plan.actions == (PlayerAction("media_player.group", ActionKind.VOLUME, 0.6, 0.25),)


def test_release_does_not_restore_a_group_player_whose_volume_was_changed() -> None:
    ducked = duck([sync_group(0.5), player("media_player.a", 0.6), player("media_player.b", 0.4)]).ducked
    assert plan_release("kitchen", ducked, {"media_player.group": current(0.9)}).actions == ()


def test_group_player_survives_storage() -> None:
    ducked = duck([sync_group(0.5), player("media_player.a", 0.6), player("media_player.b", 0.4)]).ducked
    assert ducked_from_data(ducked_to_data(ducked)) == ducked
