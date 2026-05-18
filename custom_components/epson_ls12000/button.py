"""Button entities for lens/image memory recall."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EpsonRuntimeData
from .const import DOMAIN
from .entity import EpsonEntity
from .escvp21 import EscVpError

_LOGGER = logging.getLogger(__name__)

# POPMEM x1 x2 where x1=02 (Advanced/image memory) and x2=01..0A.
# LS12000 also has lens memory under a different POPGC path but the docs
# show POPGC as N/A for this model; image memory is what users have.
_IMAGE_MEMORIES = [("01", "1"), ("02", "2"), ("03", "3"), ("04", "4"), ("05", "5")]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: EpsonRuntimeData = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = [
        EpsonImageMemoryButton(runtime, slot, label)
        for slot, label in _IMAGE_MEMORIES
    ]
    async_add_entities(entities)


class EpsonImageMemoryButton(EpsonEntity, ButtonEntity):
    """Recall a saved image-memory preset via POPMEM 02 <slot>."""

    def __init__(
        self, runtime: EpsonRuntimeData, slot: str, label: str
    ) -> None:
        super().__init__(runtime.coordinator, f"image_memory_{slot}")
        self._runtime = runtime
        self._slot = slot
        self._attr_name = f"Recall Image Memory {label}"

    @property
    def available(self) -> bool:
        data = self.coordinator.data or {}
        return data.get("power") == "on"

    async def async_press(self) -> None:
        try:
            await self._runtime.escvp.command(
                f"POPMEM 02 {self._slot}", timeout=10.0
            )
        except EscVpError as err:
            _LOGGER.error("POPMEM 02 %s failed: %s", self._slot, err)
            return
        await self.coordinator.async_request_refresh()
