<h1><img src="custom_components/duck_my_music/brand/icon.png" alt="Duck My Music icon" width="48" height="48" align="center"> Duck My Music</h1>

A Home Assistant custom integration that lowers ("ducks") the music in a room while a voice satellite in that room is listening or speaking, and restores it afterwards.

> **Status: beta version, first implementation. Use with care.** The behavior is described in [docs/behavior.md](docs/behavior.md), the design and the open points in [docs/plan.md](docs/plan.md).

## Example

The music of a player is lowered while the satellite in its room is busy and restored afterwards. Both steps show on the player's activity:

![Activity of a player: the volume was lowered from 10 % to 5 % and restored by Duck My Music](docs/example_protocol.jpg)

## What it is meant to do

When an ESPHome Assist satellite (Linux Voice Assistant, Voice PE, your own ESPHome firmware) leaves `idle`, for example after a wake word:

- Every other `media_player` in the same area that is **playing** is lowered to 50 % of its own volume.
- When the satellite is `idle` again, the volumes are restored.
- The satellite that speaks lowers its own music locally. The integration does not touch it.
- All volumes are read in one step and every target is computed from that snapshot, so players that are synchronized behind the scenes are not lowered twice.

Neither the ESPHome native API nor Sendspin has a duck/unduck command, so the integration sets the volume itself.

## Installation

Needs Home Assistant 2025.10 or newer.

1. [![Open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=florian-asche&repository=integration-duck-my-music&category=integration)
   In Home Assistant's [Marketplace](https://www.home-assistant.io/integrations/marketplace/) (**Settings** > **Marketplace** > **Add from link**), add `https://github.com/florian-asche/integration-duck-my-music` and install **Duck My Music**.
2. [![Set up the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=duck_my_music)
   Add **Duck My Music** under **Settings** > **Devices & services**. There is nothing to configure; the options are on the entry afterwards.

## Requirements

- The satellites and the players must be in an **area** (on the entity or on its device). Satellites without an area are ignored.
- Satellites are ESPHome `assist_satellite` entities. Players are ESPHome and Music Assistant (Sendspin) `media_player` entities that support setting the volume.

## Activity

Everything the integration does to a player shows in that player's **Activity** (logbook), for example *Media Player volume lowered by Duck My Music from 60 % to 30 % because a satellite in the room is busy*, *… volume restored by Duck My Music from 30 % to 60 %*, *… paused by Duck My Music …* and *… resumed by Duck My Music*. Home Assistant shows the name of the player as the subject of such an entry, so the text itself names the integration. If someone changes the volume (or resumes or stops the music) while it is lowered or paused, the integration does not touch the player afterwards and writes an info message to the log. Detailed decisions are in the debug log of `custom_components.duck_my_music`. To see them, add this to `configuration.yaml` and restart:

```yaml
logger:
  logs:
    custom_components.duck_my_music: debug
```

## Options

| Option | Default | Meaning |
|---|---|---|
| What to do with the music | Lower the volume | *Lower the volume*, or *Pause and resume*: the players that play are paused while the satellite is busy and resumed afterwards. A player is only resumed if it is still paused. |
| Lower the volume by | 50 % | Only when lowering: each playing player loses this share of its **own** volume. |
| Restore delay | 0 s | Wait this long after the satellite is idle before restoring. |
| Players that are never lowered | none | For example the player of the satellite that speaks, if it shows up a second time. |

## Development

Tests need Python 3.14 and the pinned test requirements:

```bash
uv venv -p 3.14 && uv pip install -r requirements_test.txt
.venv/bin/pytest
```

## License

Apache-2.0, see [LICENSE](LICENSE).
