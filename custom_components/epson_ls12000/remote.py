"""Remote entity exposing raw ESC/VP21 send_command capability."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import RemoteEntity, RemoteEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EpsonRuntimeData
from .const import DOMAIN, KEY_CODES
from .entity import EpsonEntity
from .escvp21 import EscVpError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: EpsonRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EpsonRemote(runtime)])


class EpsonRemote(EpsonEntity, RemoteEntity):
    """Sends raw ESC/VP21 commands, including KEY xx remote codes.

    `command:` accepts either:
      - a known key name from KEY_CODES (e.g. 'menu', 'enter') -> sends 'KEY xx'
      - an ESC/VP21 verb with parameter (e.g. 'PWR ON', 'SOURCE 30')
    """

    _attr_name = "Remote"
    _attr_supported_features = RemoteEntityFeature(0)

    def __init__(self, runtime: EpsonRuntimeData) -> None:
        super().__init__(runtime.coordinator, "remote")
        self._runtime = runtime

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        return data.get("power") in ("on", "warmup")

    async def async_turn_on(self, activity: str | None = None, **kwargs: Any) -> None:
        await self._power(True)

    async def async_turn_off(self, activity: str | None = None, **kwargs: Any) -> None:
        await self._power(False)

    async def async_send_command(
        self, command: Iterable[str], **kwargs: Any
    ) -> None:
        for raw in command:
            body = self._translate(raw)
            if body in ("PWR ON", "PWR OFF"):
                await self._power(body == "PWR ON")
            else:
                await self._send_escvp(body)

    @staticmethod
    def _translate(raw: str) -> str:
        token = raw.strip()
        code = KEY_CODES.get(token.lower())
        if code:
            return f"KEY {code}"
        return token

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
