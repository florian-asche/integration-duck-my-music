# Satellite Controller

A Home Assistant custom integration that lowers ("ducks") the music in a room while a voice satellite in that room is listening or speaking, and restores it afterwards.

> **Status: skeleton.** The integration sets up and tears down, but the ducking is not implemented yet. The design is in [docs/plan.md](docs/plan.md).

## What it is meant to do

When an ESPHome Assist satellite (Linux Voice Assistant, Voice PE, your own ESPHome firmware) leaves `idle`, for example after a wake word:

- Every other `media_player` in the same area that is **playing** is lowered to 50 % of its own volume.
- When the satellite is `idle` again, the volumes are restored.
- The satellite that speaks lowers its own music locally. The integration does not touch it.
- Sendspin players that are in the same group are handled once per group, because changing one member changes the whole group.

Neither the ESPHome native API nor Sendspin has a duck/unduck command, so the integration sets the volume itself.

## Installation

Not usable yet. It is planned to be installable through HACS as a custom repository.

## Development

Tests need Python 3.14 and the pinned test requirements:

```bash
uv venv -p 3.14 && uv pip install -r requirements_test.txt
.venv/bin/pytest
```

## License

Apache-2.0, see [LICENSE](LICENSE).
