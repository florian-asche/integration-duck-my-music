# Satellite Controller: plan

Status: milestones 1-5 are implemented (see section 10). Hardware measurement (milestone 0) and hardware tests (milestone 6) are not done. Items marked *unverified* have not been confirmed against source code or hardware.

## 1. Goal

Per room (Home Assistant area), lower the music while a voice satellite in that room is busy, and restore it afterwards.

- Trigger: an ESPHome Assist satellite changes from `idle` to `listening`, `processing` or `responding`. This covers wake word, request, TTS reply, announcements and `start_conversation`.
- Effect: every other `media_player` in the same area that is **playing** is lowered to 50 % of its **own** current volume.
- End: the satellite is `idle` again, so the volumes are restored.
- Music only. Announcements, TTS and timer sounds are not touched.
- Targets: Sendspin players (through Music Assistant, including groups) and normal ESPHome `media_player` entities.

## 2. Verified facts

| Fact | Source |
|---|---|
| The ESPHome native API has no duck command. `MediaPlayerCommand` has play, pause, stop, mute, unmute, toggle, volume up/down, enqueue, repeat, clear playlist. `MediaPlayerCommandRequest` can set an absolute volume. | `esphome/components/api/api.proto` |
| Voice PE ducks internally with `mixer_speaker.apply_ducking`. It is not reachable from Home Assistant. | `esphome/home-assistant-voice-pe` |
| `AssistSatelliteState`: `idle`, `listening`, `processing`, `responding`. | `homeassistant/components/assist_satellite/entity.py` |
| Sendspin has no duck command. Player commands are `volume`, `mute`, `set_output_delay`. Ducking appears only as a local, temporary output effect of a client. | `Sendspin/spec` |
| Sendspin: every client is in exactly one group. The group volume command applies a delta to all members. | `Sendspin/spec` |
| Music Assistant `volume_set` on a normal player sets only that player (one `server/command` to that client). On a `GROUP` player it redirects to the group volume, which scales the members proportionally from a snapshot. | `music_assistant/controllers/players/volume.py`, `aiosendspin` |
| The Music Assistant HA entity exposes `group_members` (entity ids). For a `GROUP` player `volume_level` is the group volume. | `homeassistant/components/music_assistant/media_player.py` |
| The effective area of an entity is `entity_registry.async_get_effective_area_id(hass, entry)` (entity area, else device area including parent devices). | `homeassistant/helpers/entity_registry.py` |
| Third-party precedent: Kiosk Satellite ducks Music Assistant, Home Assistant and Sonos players with temporary volume commands. | `jxlarrea/kiosk-satellite` |

**Open contradiction (unverified):** the maintainer observes that setting the volume of one Sendspin member writes the same value to all devices of the group. The Music Assistant and aiosendspin code does not show this for `players/cmd/volume_set` on a single player. Possible explanations: the observed entity was a group player or the ESPHome Sendspin group player, or a device follows the group value. This is measured before any code is written (milestone 0).

## 3. Strategy per device type

The speaking satellite ducks its own music locally. The integration only lowers the **other** players in the room that are playing.

| Device type | Detection | Duck | Restore |
|---|---|---|---|
| ESPHome `media_player`, no Sendspin | platform `esphome`, domain `media_player`, state `playing` | `volume_set(snapshot × 0.5)` | `volume_set(snapshot)` |
| Sendspin player via Music Assistant | platform `music_assistant`, groups via attribute `group_members` | One command per group on one device of the group | `volume_set(snapshot)` on that device |

Rules:

1. The reduction is relative: target = the device's own volume × 0.5 (default). The source is always the snapshot value of that device.
2. A device is touched only if its `media_player` is `playing`. Paused, stopped, off or unavailable players are left alone and are not restored either. A player that starts during ducking is ducked afterwards.
3. Players without the `VOLUME_SET` feature are skipped.
4. **Groups are one unit.** Because changing one member changes the others, a group is handled once: pick a single device of the group (preferably one that is in the satellite's room and playing), read its volume, set half of it. The other members are neither read nor set. Restore sets the same device back.
5. Group entities (Music Assistant `GROUP` players, the ESPHome Sendspin group player) are never targets themselves, otherwise the reduction would be applied twice.
6. If a group spans several rooms, all of it is lowered (it moves together). Options: duck the whole group (default) or skip groups that span several rooms and log it.
7. Members with different volumes before ducking are equal after restore. This edge case is accepted and documented.
8. If the user changes a volume while ducked (current value differs from the ducked value), the stored entry is dropped and not restored.
9. The snapshot is persisted in a `Store`, so a restart of Home Assistant during ducking does not leave the music quiet.

How to tell which entities are in the same Sendspin group is *unverified*. Start with `group_members` and the entity registry. If that is not enough, read Music Assistant's own player data (`entry.runtime_data.mass.players`, `player.type`) as the voice incubator integration does in `music.py`.

The same hardware can appear as an ESPHome `media_player` and as a Music Assistant player (same MAC). Ducking both would reduce twice. Merge by MAC (`CONNECTION_NETWORK_MAC`) and prefer the Sendspin player when it plays (*unverified*).

## 4. Architecture

- `integration_type: service`, `iot_class: local_push`, `single_config_entry: true`, `config_flow: true`, `after_dependencies` `assist_satellite` and `media_player` (only load order, no hard dependency: the integration reads entity states and calls `media_player.volume_set`, it only imports the `MediaPlayerEntityFeature` constants and compares the satellite states as strings). No external requirements, no YAML. Tests therefore need nothing beyond `pytest-homeassistant-custom-component`.
- State changes of all ESPHome `assist_satellite` entities are tracked with `async_track_state_change_event`. New satellites are found through registry events. Each satellite's area comes from `async_get_effective_area_id`. Satellites without an area are ignored (reported in diagnostics).
- Per area the active satellites are counted (set of entity ids, not a flag): duck on the first, restore on the last.
- Pure logic (`areas.py`, `ducking.py`) takes data and returns a list of actions, with no Home Assistant access. Side effects live in `controller.py` only.
- Planned files: `areas.py`, `ducking.py`, `controller.py`, `diagnostics.py`, optional `switch.py` (per area on/off).

## 5. Options (UI)

- Ducking strength (default 50 %: each device is lowered by 50 % of its own volume).
- Restore delay after `idle` (default 0 s), useful for follow-up conversations.
- Excluded players (for example a satellite's own player when it shows up a second time).
- Groups that span several rooms: duck all or skip.

## 6. Open design questions

- Latency: wake word, ESPHome, Home Assistant, `volume_set`, player. Slower than the local ducking of the satellites. The earliest signal is `listening` (*unverified* whether that is acceptable).
- Gentle ducking (a ramp over about 300 ms) after the basic version works.
- Whether another satellite in the room that only plays music counts as a normal player (proposal: yes, `playing` is enough).

## 7. Quality, tests, CI

- Tests with `pytest-homeassistant-custom-component`, one test file per module. Scenarios: one satellite; two satellites at the same time in one area; satellite without area; player without `VOLUME_SET`; user changes volume during ducking; restart during ducking; satellite becomes `unavailable`; group with several members; group over several areas.
- CI: `hassfest`, `hacs/action`, pytest.
- Orientation: the 20 bronze rules of the quality scale (`action-setup`, `appropriate-polling`, `brands`, `common-modules`, `config-flow`, `config-flow-test-coverage`, `dependency-transparency`, `docs-*`, `entity-event-setup`, `entity-unique-id`, `has-entity-name`, `runtime-data`, `test-before-configure`, `test-before-setup`, `unique-config-entry`). Relevant here: `runtime-data`, config flow with tests, `unique-config-entry`, clean unloading of listeners, documentation.

## 8. Milestones

0. **Measurement with real hardware (before any code):** a Sendspin group with 2-3 devices. Set a volume through the Music Assistant player entity, the Music Assistant group entity and the ESPHome entity, and read all member volumes: same value, delta or proportional? How long until all values show in Home Assistant?
1. Skeleton (done): manifest, config flow, CI.
2. Satellites and players per area (done: `activity.py`, `players.py`; the area comes from Home Assistant's `async_get_effective_area_id`).
3. `ducking.py` with tests: plan and restore, owners, several satellites, groups (done).
4. `controller.py`: state listeners, service calls, persistence (done).
5. Options flow and translations (done). Diagnostics not done.
6. Hardware test: Linux Voice Assistant with a Sendspin group, Voice PE with an ESPHome player; measure latency.
7. README with examples, optional ramp, optional per-area switch.

## 9. Non-goals

- No control of the satellites themselves (Linux Voice Assistant and ESPHome duck their own music locally).
- No change to ESPHome firmware or the ESPHome protocol. A real `duck` command would have to be added upstream.
- No pausing instead of ducking (at most a later option).

## 10. Implementation status

Implemented:

- `activity.py`: which satellites are busy per area (pure).
- `ducking.py`: `plan_duck` and `plan_release` (pure). One device per group, group players never the target, relative reduction, only playing players with volume control, restore only when the volume is still the ducked one, several areas can share a lowered group.
- `players.py`: reads the ESPHome and Music Assistant `media_player` states and areas.
- `controller.py`: follows `assist_satellite` (platform `esphome`) and `media_player` states, ducks on the first busy satellite of an area, restores on the last, ducks players that start playing meanwhile, restore delay, restores on unload, persists the lowered players in a `Store` and restores them at startup.
- Options flow: mode (lower or pause), strength, restore delay, excluded players, skip groups that span several rooms.
- Pause mode: the playing player of each group in the room is paused with `media_player.media_pause` and resumed with `media_player.media_play` once the area is quiet, only if it is still paused. Needs the `PAUSE` feature, not volume control. Pausing a Sendspin group member is assumed to pause the whole group (*unverified*).
- Activity: every volume change, pause and resume fires a `logbook_entry` event for the player, so it shows on the player's and its device's activity.

Heuristics that are not verified with hardware:

- A Music Assistant group player is recognised as an entity that lists members but is not one of them. If Music Assistant also lists the leader or the group player itself, this has to be adjusted.
- Players in the same group are found through the `group_members` attribute only.

Not done:

- Milestone 0 (measurement) and milestone 6 (hardware test, latency).
- Merging the same hardware that shows up as an ESPHome player and as a Music Assistant player. Exclude the duplicate in the options until then.
- Ducking while a timer rings, a per-area on/off switch, a volume ramp, diagnostics.
