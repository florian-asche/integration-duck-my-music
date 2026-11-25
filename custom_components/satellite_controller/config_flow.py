"""Config flow for Satellite Controller: one entry, and options for how the music is lowered."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
)

from .const import (
    CONF_DUCK_PERCENT,
    CONF_EXCLUDED_ENTITIES,
    CONF_MODE,
    CONF_RESTORE_DELAY,
    DEFAULT_DUCK_PERCENT,
    DEFAULT_MODE,
    DEFAULT_RESTORE_DELAY,
    DOMAIN,
    MODE_DUCK,
    MODE_PAUSE,
)


class SatelliteControllerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up Satellite Controller."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """The options of an entry."""
        return SatelliteControllerOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Create the entry after the user confirmed it."""
        if user_input is not None:
            return self.async_create_entry(title="Satellite Controller", data={})
        return self.async_show_form(step_id="user")


class SatelliteControllerOptionsFlow(OptionsFlow):
    """Whether the music is lowered or paused, how much, and for which players."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(CONF_MODE, default=options.get(CONF_MODE, DEFAULT_MODE)): SelectSelector(
                    SelectSelectorConfig(options=[MODE_DUCK, MODE_PAUSE], translation_key=CONF_MODE)
                ),
                vol.Required(CONF_DUCK_PERCENT, default=options.get(CONF_DUCK_PERCENT, DEFAULT_DUCK_PERCENT)): NumberSelector(
                    NumberSelectorConfig(min=10, max=90, step=5, unit_of_measurement="%", mode=NumberSelectorMode.SLIDER)
                ),
                vol.Required(CONF_RESTORE_DELAY, default=options.get(CONF_RESTORE_DELAY, DEFAULT_RESTORE_DELAY)): NumberSelector(
                    NumberSelectorConfig(min=0, max=10, step=0.5, unit_of_measurement="s", mode=NumberSelectorMode.SLIDER)
                ),
                vol.Required(CONF_EXCLUDED_ENTITIES, default=options.get(CONF_EXCLUDED_ENTITIES, [])): EntitySelector(
                    EntitySelectorConfig(domain="media_player", multiple=True)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
