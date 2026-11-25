# Satellite Controller

A Home Assistant custom integration that lowers ("ducks") the music in a room while a voice satellite in that room is listening or speaking, and restores it afterwards.

> **Status: first implementation, not tested with real hardware.** The design and the open points are in [docs/plan.md](docs/plan.md).

## What it is meant to do

When an ESPHome Assist satellite (Linux Voice Assistant, Voice PE, your own ESPHome firmware) leaves `idle`, for example after a wake word:

- Every other `media_player` in the same area that is **playing** is lowered to 50 % of its own volume.
- When the satellite is `idle` again, the volumes are restored.
- The satellite that speaks lowers its own music locally. The integration does not touch it.
- Sendspin players that are in the same group are handled once per group, because changing one member changes the whole group.

Neither the ESPHome native API nor Sendspin has a duck/unduck command, so the integration sets the volume itself.

## Installation

Add this repository to HACS as a custom repository (category *Integration*), install it and add **Satellite Controller** under *Settings, Devices & services*. Home Assistant 2025.10 or newer.

## Requirements

- The satellites and the players must be in an **area** (on the entity or on its device). Satellites without an area are ignored.
- Satellites are ESPHome `assist_satellite` entities. Players are ESPHome and Music Assistant (Sendspin) `media_player` entities that support setting the volume.

## Options

| Option | Default | Meaning |
|---|---|---|
| Lower the volume by | 50 % | Each playing player loses this share of its **own** volume. |
| Restore delay | 0 s | Wait this long after the satellite is idle before restoring. |
| Players that are never lowered | none | For example the player of the satellite that speaks, if it shows up a second time. |
| Skip groups that span several rooms | off | A group is lowered as a whole, also in other rooms. Turn on to leave such groups alone. |

## Development

Tests need Python 3.14 and the pinned test requirements:

```bash
uv venv -p 3.14 && uv pip install -r requirements_test.txt
.venv/bin/pytest
```

## License

Apache-2.0, see [LICENSE](LICENSE).
