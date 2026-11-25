"""Tests for the busy-satellite tracking."""

from custom_components.satellite_controller.activity import update_activity


def test_satellite_becoming_busy_starts_its_area() -> None:
    change = update_activity({}, "assist_satellite.a", "kitchen", "listening")
    assert change.active == {"kitchen": frozenset({"assist_satellite.a"})}
    assert change.started_areas == {"kitchen"}
    assert change.ended_areas == frozenset()


def test_every_busy_state_counts() -> None:
    for state in ("listening", "processing", "responding"):
        assert update_activity({}, "assist_satellite.a", "kitchen", state).started_areas == {"kitchen"}


def test_second_satellite_in_a_busy_area_starts_nothing() -> None:
    active = {"kitchen": frozenset({"assist_satellite.a"})}
    change = update_activity(active, "assist_satellite.b", "kitchen", "listening")
    assert change.active["kitchen"] == {"assist_satellite.a", "assist_satellite.b"}
    assert change.started_areas == frozenset()


def test_area_ends_only_with_its_last_satellite() -> None:
    active = {"kitchen": frozenset({"assist_satellite.a", "assist_satellite.b"})}
    first = update_activity(active, "assist_satellite.a", "kitchen", "idle")
    assert first.ended_areas == frozenset()
    last = update_activity(first.active, "assist_satellite.b", "kitchen", "idle")
    assert last.ended_areas == {"kitchen"}
    assert last.active == {}


def test_unavailable_satellite_is_not_busy() -> None:
    active = {"kitchen": frozenset({"assist_satellite.a"})}
    assert update_activity(active, "assist_satellite.a", "kitchen", "unavailable").ended_areas == {"kitchen"}


def test_satellite_that_moves_area_ends_the_old_one() -> None:
    active = {"kitchen": frozenset({"assist_satellite.a"})}
    change = update_activity(active, "assist_satellite.a", "bedroom", "listening")
    assert change.started_areas == {"bedroom"}
    assert change.ended_areas == {"kitchen"}


def test_satellite_without_area_is_ignored() -> None:
    change = update_activity({}, "assist_satellite.a", None, "listening")
    assert change.active == {}
    assert change.started_areas == frozenset()
