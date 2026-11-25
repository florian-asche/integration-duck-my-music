"""Connects busy satellites to the volume of the players in their room.

Listens to the state of the ESPHome Assist satellites and of the media
players. When the first satellite of an area becomes busy the players there
are lowered, when the last one is quiet again they are restored. The decisions
are made in ducking.py and activity.py, this module reads Home Assistant and
applies the result.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_LOGBOOK_ENTRY, EVENT_STATE_CHANGED
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .activity import update_activity
from .const import (
    CONF_DUCK_PERCENT,
    CONF_EXCLUDED_ENTITIES,
    CONF_MODE,
    CONF_RESTORE_DELAY,
    DEFAULT_DUCK_PERCENT,
    DEFAULT_MODE,
    DEFAULT_RESTORE_DELAY,
    DOMAIN,
    SATELLITE_PLATFORM,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .ducking import ActionKind, DuckedPlayer, DuckPlan, PlayerAction, ducked_from_data, ducked_to_data, plan_duck, plan_release
from .logbook import LOGBOOK_NAME, describe_action
from .players import collect_players, current_players

_LOGGER = logging.getLogger(__name__)


class SatelliteController:
    """Lowers and restores the players of the areas whose satellites are busy."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._lock = asyncio.Lock()
        self._active: Mapping[str, frozenset[str]] = {}
        self._satellite_devices: dict[str, str | None] = {}
        self._ducked: Mapping[str, DuckedPlayer] = {}
        self._restore_timers: dict[str, CALLBACK_TYPE] = {}
        self._unsubscribe: Callable[[], None] | None = None

    async def async_start(self) -> None:
        """Restore what an earlier run left lowered, then follow the states."""
        data = await self._store.async_load() or {}
        self._ducked = ducked_from_data(data.get("ducked", []))
        if self._ducked:
            async with self._lock:
                await self._async_release(None)
        self._unsubscribe = self._hass.bus.async_listen(EVENT_STATE_CHANGED, self._handle_state_changed, event_filter=_is_relevant)

    async def async_stop(self) -> None:
        """Stop following and give every lowered player its volume back."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        for cancel in self._restore_timers.values():
            cancel()
        self._restore_timers.clear()
        async with self._lock:
            await self._async_release(None)

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        entity_id: str = event.data["entity_id"]
        new_state = event.data["new_state"]
        if entity_id.startswith("assist_satellite."):
            self._handle_satellite(entity_id, new_state.state if new_state is not None else "unavailable")
        elif new_state is not None and new_state.state == "playing":
            old_state = event.data["old_state"]
            if old_state is None or old_state.state != "playing":
                for area_id in self._active:
                    self._entry.async_create_task(self._hass, self._async_duck(area_id))

    @callback
    def _handle_satellite(self, entity_id: str, state: str) -> None:
        entry = er.async_get(self._hass).async_get(entity_id)
        if entry is None or entry.platform != SATELLITE_PLATFORM:
            return
        area_id = er.async_get_effective_area_id(self._hass, entry)
        if area_id is None:
            _LOGGER.debug("Satellite '%s' has no area, ignored", entity_id)
            return
        self._satellite_devices[entity_id] = entry.device_id
        change = update_activity(self._active, entity_id, area_id, state)
        self._active = change.active
        for started in change.started_areas:
            _LOGGER.debug("Satellite '%s' is %s, area '%s' is busy", entity_id, state, started)
            if (cancel := self._restore_timers.pop(started, None)) is not None:
                cancel()
            self._entry.async_create_task(self._hass, self._async_duck(started))
        for ended in change.ended_areas:
            _LOGGER.debug("Satellite '%s' is %s, area '%s' is quiet", entity_id, state, ended)
            self._schedule_restore(ended)

    @callback
    def _schedule_restore(self, area_id: str) -> None:
        delay = float(self._entry.options.get(CONF_RESTORE_DELAY, DEFAULT_RESTORE_DELAY))
        if delay <= 0:
            self._entry.async_create_task(self._hass, self._async_restore(area_id))
            return

        @callback
        def _fire(_now: Any) -> None:
            self._restore_timers.pop(area_id, None)
            self._entry.async_create_task(self._hass, self._async_restore(area_id))

        self._restore_timers[area_id] = async_call_later(self._hass, delay, _fire)

    async def _async_duck(self, area_id: str) -> None:
        async with self._lock:
            if area_id not in self._active:
                _LOGGER.debug("Area '%s' is quiet again, not lowering", area_id)
                return
            options = self._entry.options
            devices = {self._satellite_devices.get(satellite) for satellite in self._active[area_id]}
            plan = plan_duck(
                collect_players(self._hass),
                area_id,
                float(options.get(CONF_DUCK_PERCENT, DEFAULT_DUCK_PERCENT)) / 100,
                set(options.get(CONF_EXCLUDED_ENTITIES, [])),
                {device for device in devices if device is not None},
                self._ducked,
                options.get(CONF_MODE, DEFAULT_MODE),
            )
            _LOGGER.debug("Area '%s': %d volume changes planned, %d players lowered afterwards", area_id, len(plan.actions), len(plan.ducked))
            await self._async_apply(plan)

    async def _async_restore(self, area_id: str) -> None:
        async with self._lock:
            if area_id in self._active:
                _LOGGER.debug("Area '%s' is busy again, not restoring", area_id)
                return
            _LOGGER.debug("Restoring area '%s', %d players lowered", area_id, len(self._ducked))
            await self._async_release(area_id)

    async def _async_release(self, area_id: str | None) -> None:
        """Restore the players of an area, or of all areas. Call with the lock held."""
        current = current_players(self._hass, list(self._ducked))
        await self._async_apply(plan_release(area_id, self._ducked, current))

    async def _async_apply(self, plan: DuckPlan) -> None:
        self._ducked = plan.ducked
        await asyncio.gather(*(self._async_perform(action) for action in plan.actions))
        await self._store.async_save({"ducked": ducked_to_data(self._ducked)})

    async def _async_perform(self, action: PlayerAction) -> None:
        """Call the media player service for an action and, if it worked, show it on the player's activity."""
        service, data = _service_call(action)
        _LOGGER.debug("Calling media_player.%s for '%s' %s", service, action.entity_id, data)
        try:
            await self._hass.services.async_call("media_player", service, data, blocking=True)
        except HomeAssistantError as err:
            _LOGGER.warning("Could not call media_player.%s for '%s': %s", service, action.entity_id, err)
            return
        message = describe_action(action)
        _LOGGER.debug("Logbook entry for '%s': %s %s", action.entity_id, LOGBOOK_NAME, message)
        self._hass.bus.async_fire(EVENT_LOGBOOK_ENTRY, {"name": LOGBOOK_NAME, "message": message, "domain": DOMAIN, "entity_id": action.entity_id})


def _service_call(action: PlayerAction) -> tuple[str, dict[str, Any]]:
    """The media_player service and its data for an action."""
    if action.kind is ActionKind.PAUSE:
        return "media_pause", {"entity_id": action.entity_id}
    if action.kind is ActionKind.RESUME:
        return "media_play", {"entity_id": action.entity_id}
    return "volume_set", {"entity_id": action.entity_id, "volume_level": action.volume}


@callback
def _is_relevant(data: Mapping[str, Any] | Any) -> bool:
    entity_id: str = data["entity_id"]
    return entity_id.startswith(("assist_satellite.", "media_player."))
