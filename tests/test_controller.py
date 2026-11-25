"""Tests for the controller: satellite states in, volume service calls out."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events, async_fire_time_changed, async_mock_service

from custom_components.satellite_controller.const import DOMAIN

VOLUME_SET = 4
PAUSE = 1
PLAYING = {"supported_features": VOLUME_SET | PAUSE}


def add_entity(hass: HomeAssistant, entity_id: str, platform: str, area_id: str | None, device_id: str | None = None) -> None:
    domain, name = entity_id.split(".")
    registry = er.async_get(hass)
    registry.async_get_or_create(domain, platform, name, suggested_object_id=name, original_name=name, device_id=device_id)
    if area_id is not None:
        registry.async_update_entity(entity_id, area_id=area_id)


def set_player(hass: HomeAssistant, entity_id: str, volume: float, state: str = "playing", **attributes) -> None:
    hass.states.async_set(entity_id, state, {"volume_level": volume, **PLAYING, **attributes})


async def setup_controller(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def volumes(calls) -> list[tuple[str, float]]:
    return [(call.data["entity_id"], call.data["volume_level"]) for call in calls]


async def test_busy_satellite_lowers_the_players_in_its_area_and_idle_restores_them(hass: HomeAssistant) -> None:
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    add_entity(hass, "assist_satellite.kitchen", "esphome", kitchen)
    add_entity(hass, "media_player.kitchen_music", "esphome", kitchen)
    add_entity(hass, "media_player.bedroom_music", "esphome", ar.async_get(hass).async_create("Bedroom").id)
    set_player(hass, "media_player.kitchen_music", 0.6)
    set_player(hass, "media_player.bedroom_music", 0.6)
    calls = async_mock_service(hass, "media_player", "volume_set")
    await setup_controller(hass)

    hass.states.async_set("assist_satellite.kitchen", "listening")
    await hass.async_block_till_done()
    assert volumes(calls) == [("media_player.kitchen_music", 0.3)]

    calls.clear()
    set_player(hass, "media_player.kitchen_music", 0.3)
    hass.states.async_set("assist_satellite.kitchen", "idle")
    await hass.async_block_till_done()
    assert volumes(calls) == [("media_player.kitchen_music", 0.6)]


async def test_area_stays_lowered_until_the_last_satellite_is_idle(hass: HomeAssistant) -> None:
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    for name in ("one", "two"):
        add_entity(hass, f"assist_satellite.{name}", "esphome", kitchen)
    add_entity(hass, "media_player.music", "esphome", kitchen)
    set_player(hass, "media_player.music", 0.6)
    calls = async_mock_service(hass, "media_player", "volume_set")
    await setup_controller(hass)

    hass.states.async_set("assist_satellite.one", "listening")
    hass.states.async_set("assist_satellite.two", "responding")
    await hass.async_block_till_done()
    assert volumes(calls) == [("media_player.music", 0.3)]

    calls.clear()
    set_player(hass, "media_player.music", 0.3)
    hass.states.async_set("assist_satellite.one", "idle")
    await hass.async_block_till_done()
    assert calls == []
    hass.states.async_set("assist_satellite.two", "idle")
    await hass.async_block_till_done()
    assert volumes(calls) == [("media_player.music", 0.6)]


async def test_satellite_own_player_and_satellites_of_other_integrations_are_ignored(hass: HomeAssistant) -> None:
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    entry = MockConfigEntry(domain="esphome")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("esphome", "sat")}).id
    add_entity(hass, "assist_satellite.kitchen", "esphome", kitchen, device)
    add_entity(hass, "media_player.own", "esphome", kitchen, device)
    add_entity(hass, "assist_satellite.other", "wyoming", kitchen)
    set_player(hass, "media_player.own", 0.6)
    calls = async_mock_service(hass, "media_player", "volume_set")
    await setup_controller(hass)

    hass.states.async_set("assist_satellite.kitchen", "listening")
    hass.states.async_set("assist_satellite.other", "listening")
    await hass.async_block_till_done()
    assert calls == []


async def test_player_that_starts_while_the_satellite_is_busy_is_lowered(hass: HomeAssistant) -> None:
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    add_entity(hass, "assist_satellite.kitchen", "esphome", kitchen)
    add_entity(hass, "media_player.music", "esphome", kitchen)
    set_player(hass, "media_player.music", 0.8, state="paused")
    calls = async_mock_service(hass, "media_player", "volume_set")
    await setup_controller(hass)

    hass.states.async_set("assist_satellite.kitchen", "listening")
    await hass.async_block_till_done()
    assert calls == []

    set_player(hass, "media_player.music", 0.8)
    await hass.async_block_till_done()
    assert volumes(calls) == [("media_player.music", 0.4)]


async def test_options_change_strength_and_exclusions(hass: HomeAssistant) -> None:
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    add_entity(hass, "assist_satellite.kitchen", "esphome", kitchen)
    add_entity(hass, "media_player.music", "esphome", kitchen)
    add_entity(hass, "media_player.skipped", "esphome", kitchen)
    set_player(hass, "media_player.music", 0.8)
    set_player(hass, "media_player.skipped", 0.8)
    calls = async_mock_service(hass, "media_player", "volume_set")
    await setup_controller(hass, duck_percent=75, excluded_entities=["media_player.skipped"])

    hass.states.async_set("assist_satellite.kitchen", "listening")
    await hass.async_block_till_done()
    assert volumes(calls) == [("media_player.music", 0.2)]


async def test_restore_delay_waits_before_restoring(hass: HomeAssistant, freezer) -> None:
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    add_entity(hass, "assist_satellite.kitchen", "esphome", kitchen)
    add_entity(hass, "media_player.music", "esphome", kitchen)
    set_player(hass, "media_player.music", 0.6)
    calls = async_mock_service(hass, "media_player", "volume_set")
    await setup_controller(hass, restore_delay=2)

    hass.states.async_set("assist_satellite.kitchen", "listening")
    await hass.async_block_till_done()
    calls.clear()
    set_player(hass, "media_player.music", 0.3)
    hass.states.async_set("assist_satellite.kitchen", "idle")
    await hass.async_block_till_done()
    assert calls == []

    freezer.tick(2.5)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert volumes(calls) == [("media_player.music", 0.6)]


async def test_busy_again_during_the_restore_delay_cancels_the_restore(hass: HomeAssistant, freezer) -> None:
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    add_entity(hass, "assist_satellite.kitchen", "esphome", kitchen)
    add_entity(hass, "media_player.music", "esphome", kitchen)
    set_player(hass, "media_player.music", 0.6)
    calls = async_mock_service(hass, "media_player", "volume_set")
    await setup_controller(hass, restore_delay=2)

    hass.states.async_set("assist_satellite.kitchen", "listening")
    await hass.async_block_till_done()
    calls.clear()
    set_player(hass, "media_player.music", 0.3)
    hass.states.async_set("assist_satellite.kitchen", "idle")
    hass.states.async_set("assist_satellite.kitchen", "listening")
    await hass.async_block_till_done()
    freezer.tick(2.5)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert calls == []


async def test_unloading_restores_lowered_players(hass: HomeAssistant) -> None:
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    add_entity(hass, "assist_satellite.kitchen", "esphome", kitchen)
    add_entity(hass, "media_player.music", "esphome", kitchen)
    set_player(hass, "media_player.music", 0.6)
    calls = async_mock_service(hass, "media_player", "volume_set")
    entry = await setup_controller(hass)

    hass.states.async_set("assist_satellite.kitchen", "listening")
    await hass.async_block_till_done()
    calls.clear()
    set_player(hass, "media_player.music", 0.3)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert volumes(calls) == [("media_player.music", 0.6)]


async def test_lowered_players_are_restored_after_a_restart(hass: HomeAssistant, hass_storage) -> None:
    hass_storage["satellite_controller.ducked"] = {
        "version": 1,
        "key": "satellite_controller.ducked",
        "data": {"ducked": [{"entity_id": "media_player.music", "original_volume": 0.6, "ducked_volume": 0.3, "areas": ["kitchen"]}]},
    }
    set_player(hass, "media_player.music", 0.3)
    calls = async_mock_service(hass, "media_player", "volume_set")
    await setup_controller(hass)
    assert volumes(calls) == [("media_player.music", 0.6)]


async def test_what_happens_after_the_trigger_is_logged(hass: HomeAssistant, caplog) -> None:
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    add_entity(hass, "assist_satellite.kitchen", "esphome", kitchen)
    add_entity(hass, "media_player.music", "esphome", kitchen)
    add_entity(hass, "media_player.cast", "cast", kitchen)
    set_player(hass, "media_player.music", 0.6)
    set_player(hass, "media_player.cast", 0.6)
    async_mock_service(hass, "media_player", "volume_set")
    await setup_controller(hass)

    with caplog.at_level("DEBUG", logger="custom_components.satellite_controller"):
        hass.states.async_set("assist_satellite.kitchen", "listening")
        await hass.async_block_till_done()

    assert "Ignoring media player 'media_player.cast': platform 'cast' is not one of" in caplog.text
    assert "Media player 'media_player.music' (esphome): state playing" in caplog.text
    assert "Found 1 ESPHome and Music Assistant media players" in caplog.text
    assert "Planning area" in caplog.text
    assert "Calling media_player.volume_set for 'media_player.music' {'entity_id': 'media_player.music', 'volume_level': 0.3}" in caplog.text
    assert "1 volume changes planned" in caplog.text


async def test_pause_mode_pauses_and_resumes(hass: HomeAssistant) -> None:
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    add_entity(hass, "assist_satellite.kitchen", "esphome", kitchen)
    add_entity(hass, "media_player.music", "esphome", kitchen)
    set_player(hass, "media_player.music", 0.6)
    volume_calls = async_mock_service(hass, "media_player", "volume_set")
    pause_calls = async_mock_service(hass, "media_player", "media_pause")
    play_calls = async_mock_service(hass, "media_player", "media_play")
    await setup_controller(hass, mode="pause")

    hass.states.async_set("assist_satellite.kitchen", "listening")
    await hass.async_block_till_done()
    assert [call.data["entity_id"] for call in pause_calls] == ["media_player.music"]
    assert volume_calls == []

    set_player(hass, "media_player.music", 0.6, state="paused")
    hass.states.async_set("assist_satellite.kitchen", "idle")
    await hass.async_block_till_done()
    assert [call.data["entity_id"] for call in play_calls] == ["media_player.music"]


async def test_pause_mode_does_not_resume_music_the_user_started_again(hass: HomeAssistant) -> None:
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    add_entity(hass, "assist_satellite.kitchen", "esphome", kitchen)
    add_entity(hass, "media_player.music", "esphome", kitchen)
    set_player(hass, "media_player.music", 0.6)
    async_mock_service(hass, "media_player", "media_pause")
    play_calls = async_mock_service(hass, "media_player", "media_play")
    await setup_controller(hass, mode="pause")

    hass.states.async_set("assist_satellite.kitchen", "listening")
    await hass.async_block_till_done()
    set_player(hass, "media_player.music", 0.6, state="playing")
    hass.states.async_set("assist_satellite.kitchen", "idle")
    await hass.async_block_till_done()
    assert play_calls == []


async def test_actions_show_on_the_players_activity(hass: HomeAssistant) -> None:
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    add_entity(hass, "assist_satellite.kitchen", "esphome", kitchen)
    add_entity(hass, "media_player.music", "esphome", kitchen)
    set_player(hass, "media_player.music", 0.6)
    async_mock_service(hass, "media_player", "volume_set")
    entries = async_capture_events(hass, "logbook_entry")
    await setup_controller(hass)

    hass.states.async_set("assist_satellite.kitchen", "listening")
    await hass.async_block_till_done()
    set_player(hass, "media_player.music", 0.3)
    hass.states.async_set("assist_satellite.kitchen", "idle")
    await hass.async_block_till_done()

    assert [(event.data["name"], event.data["message"], event.data["entity_id"], event.data["domain"]) for event in entries] == [
        ("Satellite Controller", "volume lowered by Satellite Controller from 60 % to 30 % because a satellite in the room is busy", "media_player.music", DOMAIN),
        ("Satellite Controller", "volume restored by Satellite Controller from 30 % to 60 %", "media_player.music", DOMAIN),
    ]


async def test_failed_service_call_leaves_no_activity_entry(hass: HomeAssistant) -> None:
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    add_entity(hass, "assist_satellite.kitchen", "esphome", kitchen)
    add_entity(hass, "media_player.music", "esphome", kitchen)
    set_player(hass, "media_player.music", 0.6)
    entries = async_capture_events(hass, "logbook_entry")
    await setup_controller(hass)

    hass.states.async_set("assist_satellite.kitchen", "listening")
    await hass.async_block_till_done()
    assert entries == []
