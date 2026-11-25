"""Constants for the Satellite Controller integration."""

DOMAIN = "satellite_controller"

STORAGE_KEY = f"{DOMAIN}.ducked"
STORAGE_VERSION = 1

CONF_MODE = "mode"
CONF_DUCK_PERCENT = "duck_percent"
CONF_RESTORE_DELAY = "restore_delay"
CONF_EXCLUDED_ENTITIES = "excluded_entities"
CONF_SKIP_MULTI_ROOM_GROUPS = "skip_multi_room_groups"

MODE_DUCK = "duck"
MODE_PAUSE = "pause"

DEFAULT_MODE = MODE_DUCK
DEFAULT_DUCK_PERCENT = 50
DEFAULT_RESTORE_DELAY = 0
DEFAULT_SKIP_MULTI_ROOM_GROUPS = False

SATELLITE_PLATFORM = "esphome"
PLAYER_PLATFORMS = frozenset({"esphome", "music_assistant"})
