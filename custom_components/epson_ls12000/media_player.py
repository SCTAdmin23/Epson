"""Media player entity for the Epson LS12000."""
from __future__ import annotations

import logging

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EpsonRuntimeData
from .const import (
    CMODE_TO_CODE,
    CODE_TO_CMODE,
    CODE_TO_SOURCE,
    DOMAIN,
    SOURCE_TO_CODE,
)
from .entity import EpsonEntity
from .escvp21 import EscVpError

_LOGGER = logging.getLogger(__name__)

_PWR_TO_STATE = {
    "on": MediaPlayerState.ON,
    "standby": MediaPlayerState.OFF,
    "network_standby": MediaPlayerState.OFF,
    "warmup": MediaPlayerState.ON,
    "cooldown": MediaPlayerState.OFF,
    "abnormal": MediaPlayerState.OFF,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: EpsonRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EpsonMediaPlayer(runtime)])


class EpsonMediaPlayer(EpsonEntity, MediaPlayerEntity):
    """Power, source, and color mode surface for the projector."""

    _attr_name = None  # uses device name
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.SELECT_SOUND_MODE
    )
    _attr_source_list = list(SOURCE_TO_CODE)
    _attr_sound_mode_list = list(CMODE_TO_CODE)

    def __init__(self, runtime: EpsonRuntimeData) -> None:
        super().__init__(runtime.coordinator, "media_player")
        self._runtime = runtime

    @property
    def state(self) -> MediaPlayerState | None:
        data = self.coordinator.data or {}
        return _PWR_TO_STATE.get(data.get("power"))

    @property
    def source(self) -> str | None:
        code = (self.coordinator.data or {}).get("source")
        return CODE_TO_SOURCE.get(code)

    @property
    def sound_mode(self) -> str | None:
        code = (self.coordinator.data or {}).get("cmode")
        return CODE_TO_CMODE.get(code)

    async def async_turn_on(self) -> None:
        await self._power(True)

    async def async_turn_off(self) -> None:
        await self._power(False)

    async def async_select_source(self, source: str) -> None:
        code = SOURCE_TO_CODE.get(source)
        if code is None:
            _LOGGER.warning("Unknown source: %s", source)
            return
        await self._send_escvp(f"SOURCE {code}")

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        code = CMODE_TO_CODE.get(sound_mode)
        if code is None:
            return
        await self._send_escvp(f"CMODE {code}")

    async def _power(self, on: bool) -> None:
        try:
            await self._runtime.power(on)
        except EscVpError as err:
            _LOGGER.error("Power %s failed on both protocols: %s",
                          "on" if on else "off", err)
            return
        await self.coordinator.async_request_refresh()

    async def _send_escvp(self, body: str) -> None:
        try:
            await self._runtime.escvp.command(body, timeout=10.0)
        except EscVpError as err:
            _LOGGER.error("ESC/VP21 command %r failed: %s", body, err)
            return
        await self.coordinator.async_request_refresh()
