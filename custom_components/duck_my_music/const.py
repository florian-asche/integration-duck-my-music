"""Constants for the Duck My Music integration."""

DOMAIN = "duck_my_music"

STORAGE_KEY = f"{DOMAIN}.ducked"
STORAGE_VERSION = 1

CONF_MODE = "mode"
CONF_DUCK_PERCENT = "duck_percent"
CONF_RESTORE_DELAY = "restore_delay"
CONF_EXCLUDED_ENTITIES = "excluded_entities"

MODE_DUCK = "duck"
MODE_PAUSE = "pause"

DEFAULT_MODE = MODE_DUCK
DEFAULT_DUCK_PERCENT = 50
DEFAULT_RESTORE_DELAY = 0

SATELLITE_PLATFORM = "esphome"
PLAYER_PLATFORMS = frozenset({"esphome", "music_assistant"})
