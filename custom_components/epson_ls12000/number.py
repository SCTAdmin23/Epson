"""Number entities for picture adjustments (LUMLEVEL etc.)."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EpsonRuntimeData
from .const import DOMAIN
from .entity import EpsonEntity
from .escvp21 import EscVpError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: EpsonRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EpsonLumLevel(runtime)])


class EpsonLumLevel(EpsonEntity, NumberEntity):
    """Light-source brightness 0-255 (ESC/VP21 LUMLEVEL)."""

    _attr_name = "Light Output"
    _attr_native_min_value = 0
    _attr_native_max_value = 255
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, runtime: EpsonRuntimeData) -> None:
        super().__init__(runtime.coordinator, "lumlevel")
        self._runtime = runtime

    @property
    def available(self) -> bool:
        data = self.coordinator.data or {}
        return data.get("power") == "on"

    @property
    def native_value(self) -> float | None:
        raw = (self.coordinator.data or {}).get("lumlevel")
        try:
            return float(raw) if raw is not None else None
        except ValueError:
            return None

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self._runtime.escvp.command(
                f"LUMLEVEL {int(value)}", timeout=10.0
            )
        except EscVpError as err:
            _LOGGER.error("LUMLEVEL set failed: %s", err)
            return
        await self.coordinator.async_request_refresh()
