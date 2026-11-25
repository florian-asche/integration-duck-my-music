"""Tests for planning how to lower and restore the players."""

import logging

import pytest

from custom_components.satellite_controller.ducking import (
    DuckedPlayer,
    PlayerSnapshot,
    VolumeAction,
    ducked_from_data,
    ducked_to_data,
    plan_duck,
    plan_release,
)


def player(entity_id: str, volume: float | None = 0.6, area_id: str | None = "kitchen", **kwargs) -> PlayerSnapshot:
    values = {"device_id": None, "playing": True, "can_set_volume": True, "group_members": ()}
    values.update(kwargs)
    return PlayerSnapshot(entity_id=entity_id, area_id=area_id, volume=volume, **values)


def duck(players, ducked=None, area_id="kitchen", skip_multi_room_groups=False, excluded_entities=(), excluded_devices=()):
    return plan_duck(players, area_id, 0.5, set(excluded_entities), set(excluded_devices), ducked or {}, skip_multi_room_groups)


def test_playing_player_is_lowered_by_half_of_its_own_volume() -> None:
    plan = duck([player("media_player.a", 0.6), player("media_player.b", 0.4)])
    assert plan.actions == (VolumeAction("media_player.a", 0.3), VolumeAction("media_player.b", 0.2))
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
    assert plan.actions == (VolumeAction("media_player.a", 0.3),)
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
    plan = plan_release("kitchen", ducked, {"media_player.a": 0.3})
    assert plan.actions == (VolumeAction("media_player.a", 0.6),)
    assert plan.ducked == {}


def test_release_does_not_restore_a_volume_changed_meanwhile(caplog: pytest.LogCaptureFixture) -> None:
    ducked = duck([player("media_player.a", 0.6)]).ducked
    with caplog.at_level(logging.DEBUG):
        plan = plan_release("kitchen", ducked, {"media_player.a": 0.8})
    assert plan.actions == ()
    assert plan.ducked == {}
    assert "Not restoring 'media_player.a'" in caplog.text


def test_release_skips_players_that_are_gone() -> None:
    ducked = duck([player("media_player.a", 0.6)]).ducked
    assert plan_release("kitchen", ducked, {"media_player.a": None}).actions == ()


def test_release_keeps_a_player_another_area_still_needs() -> None:
    ducked = {"media_player.a": DuckedPlayer("media_player.a", 0.6, 0.3, frozenset({"kitchen", "bedroom"}))}
    plan = plan_release("kitchen", ducked, {"media_player.a": 0.3})
    assert plan.actions == ()
    assert plan.ducked["media_player.a"].areas == {"bedroom"}


def test_release_of_all_areas() -> None:
    ducked = {"media_player.a": DuckedPlayer("media_player.a", 0.6, 0.3, frozenset({"kitchen", "bedroom"}))}
    plan = plan_release(None, ducked, {"media_player.a": 0.3})
    assert plan.actions == (VolumeAction("media_player.a", 0.6),)


def test_ducked_players_survive_storage() -> None:
    ducked = {"media_player.a": DuckedPlayer("media_player.a", 0.6, 0.3, frozenset({"kitchen", "bedroom"}))}
    assert ducked_from_data(ducked_to_data(ducked)) == ducked
