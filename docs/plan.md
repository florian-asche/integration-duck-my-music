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
| Sendspin player via Music Assistant | platform `music_assistant`, state `playing` | `volume_set(snapshot × 0.5)` on every playing player | `volume_set(snapshot)` on each |

Rules:

1. The reduction is relative: target = the device's own volume × 0.5 (default). The source is always the snapshot value of that device.
2. A device is touched only if its `media_player` is `playing`. Paused, stopped, off or unavailable players are left alone and are not restored either. A player that starts during ducking is ducked afterwards.
3. Players without the `VOLUME_SET` feature are skipped.
4. **One snapshot, then one change per player (decision 2026-11-25).** Temporarily assembled Sendspin players are not fixed groups, so a group is not treated as a unit. The volumes of all matching players are read in one step (no waiting between the reads), every target is computed from that snapshot and never from a volume an earlier change may have moved, and then each player is set on its own. If players are synchronized behind the scenes, the changes do not multiply (no 50 % of 50 %); the players that are synchronized end up at the value that was set last.
5. Entities that only represent a group (Music Assistant `GROUP` players, the ESPHome Sendspin group player) are never targets themselves, otherwise their children would be lowered twice. They are recognised as entities that list `group_members` without being one of them.
6. Restore sets every player back to its snapshot volume. A player counts as unchanged if its current volume equals any of the lowered volumes, because a synchronized player can end up at the volume of another one.
7. The reads and the changes are not repeated or verified afterwards.
8. If the user changes a volume while ducked (current value differs from the ducked value), the stored entry is dropped and not restored.
9. The snapshot is persisted in a `Store`, so a restart of Home Assistant during ducking does not leave the music quiet.

How to recognise an entity that only represents a group is *unverified*; if the heuristic in rule 5 is not enough, read Music Assistant's own player data (`entry.runtime_data.mass.players`, `player.type`) as the voice incubator integration does in `music.py`.

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
3. `ducking.py` with tests: plan and restore, owners, several satellites, one snapshot for all players (done).
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
- `ducking.py`: `plan_duck` and `plan_release` (pure). Targets from one snapshot, one change per player, group players never the target, relative reduction, only playing players with volume control, restore only when the volume is still one of the lowered volumes.
- `players.py`: reads the ESPHome and Music Assistant `media_player` states and areas.
- `controller.py`: follows `assist_satellite` (platform `esphome`) and `media_player` states, ducks on the first busy satellite of an area, restores on the last, ducks players that start playing meanwhile, restore delay, restores on unload, persists the lowered players in a `Store` and restores them at startup.
- Options flow: mode (lower or pause), strength, restore delay, excluded players.
- Pause mode: every playing player in the room is paused with `media_player.media_pause` and resumed with `media_player.media_play` once the area is quiet, only if it is still paused. Needs the `PAUSE` feature, not volume control. Pausing a Sendspin group member is assumed to pause the whole group (*unverified*).
- Activity: every volume change, pause and resume fires a `logbook_entry` event for the player, so it shows on the player's and its device's activity.

Heuristics that are not verified with hardware:

- A Music Assistant group player is recognised as an entity that lists members but is not one of them. If Music Assistant also lists the leader or the group player itself, this has to be adjusted.

Not done:

- Milestone 0 (measurement) and milestone 6 (hardware test, latency).
- Merging the same hardware that shows up as an ESPHome player and as a Music Assistant player. Exclude the duplicate in the options until then.
- Ducking while a timer rings, a per-area on/off switch, a volume ramp, diagnostics.

## 11. Locking the volume while lowered (research, 2026-11-25)

Question: can the volume be locked while the music is lowered, so that nothing else changes it?

Verified in the sources:

- **Home Assistant:** `media_player` has no lock. The volume slider of a player belongs to the integration that provides the entity (ESPHome, Music Assistant); this integration cannot disable or grey it out.
- **ESPHome native API:** no lock and no duck command (see section 2).
- **Sendspin spec:** no lock, no limit and no duck command. A player only declares which commands it accepts (`supported_commands`); the server cannot lock the volume of a client. Ducking is only mentioned as a local, temporary output effect of a client. Volume and mute are independent.
- **Music Assistant public API (`players/cmd/*`):** `volume_set`, `volume_up`, `volume_down`, `volume_mute`, `group_volume*`, `play_announcement`, `group`, `ungroup`, `set_members`. No lock and no duck command. Internal volume locks exist only to serialize commands. A mute lock exists internally for players in groups and is not exposed.
- **Music Assistant per-player volume limits (min/max):** a configuration of the player, not a runtime lock. They only clamp a device volume that is outside the range. Setting min and max to the ducked value through the configuration API would act like a lock, but it rewrites the user's player configuration and has to be undone reliably (also after a crash). Not recommended.
- **Music Assistant announcements (`play_announcement`):** Music Assistant lowers or raises a player for an announcement and restores the previous volume itself (strategies none, absolute, relative, percentual). That is for announcements Music Assistant plays, not for a satellite that is busy, so it does not replace this integration.

Options for this integration:

1. **Do not lock (current).** If someone changes the volume while it is lowered, the player is not restored afterwards (section 3, rule 8) and an info message says so in the log. Nothing fights the user.
2. **Revert changes while lowered (possible, not built).** Watch the volume of lowered players and set it back to the ducked value when it differs. Drawbacks: the volume flickers, a Sendspin group moves together and could start a loop with other members' reports, and it overrides a deliberate change by the user. Physical knobs and other apps cannot be stopped from changing it first.
3. **Treat a change as the new level (possible, not built).** If the volume is changed while lowered, restore to the new level divided by the ducked fraction instead of dropping the entry. Avoids fighting the user, but the result is a guess.

Recommendation: stay with option 1. Add option 2 only as an opt-in setting if it turns out to be needed.
