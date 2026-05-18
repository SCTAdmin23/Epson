"""Select entities for picture-mode / aspect / HDR / frame interpolation."""
from __future__ import annotations

import logging
from collections.abc import Mapping

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EpsonRuntimeData
from .const import (
    ASPECT_TO_CODE,
    CMODE_TO_CODE,
    CLRSPACE_TO_CODE,
    CODE_TO_ASPECT,
    CODE_TO_CLRSPACE,
    CODE_TO_CMODE,
    CODE_TO_DYNRANGE,
    CODE_TO_MCFI,
    CODE_TO_PRESET,
    DOMAIN,
    DYNRANGE_TO_CODE,
    MCFI_TO_CODE,
    PRESET_TO_CODE,
)
from .entity import EpsonEntity
from .escvp21 import EscVpError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: EpsonRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            EpsonSelect(runtime, "color_mode", "Color Mode", "CMODE",
                        CMODE_TO_CODE, CODE_TO_CMODE),
            EpsonSelect(runtime, "aspect", "Aspect", "ASPECT",
                        ASPECT_TO_CODE, CODE_TO_ASPECT),
            EpsonSelect(runtime, "dynamic_range", "Dynamic Range", "DYNRANGE",
                        DYNRANGE_TO_CODE, CODE_TO_DYNRANGE),
            EpsonSelect(runtime, "color_space", "Color Space", "CLRSPACE",
                        CLRSPACE_TO_CODE, CODE_TO_CLRSPACE),
            EpsonSelect(runtime, "frame_interpolation", "Frame Interpolation",
                        "MCFI", MCFI_TO_CODE, CODE_TO_MCFI),
            EpsonSelect(runtime, "image_preset", "Image Preset", "IMGPRESET",
                        PRESET_TO_CODE, CODE_TO_PRESET),
        ]
    )


class EpsonSelect(EpsonEntity, SelectEntity):
    """Generic select bound to a single ESC/VP21 verb + enum map."""

    def __init__(
        self,
        runtime: EpsonRuntimeData,
        key: str,
        name: str,
        verb: str,
        name_to_code: Mapping[str, str],
        code_to_name: Mapping[str, str],
    ) -> None:
        super().__init__(runtime.coordinator, f"select_{key}")
        self._runtime = runtime
        self._key = key
        self._attr_name = name
        self._verb = verb
        self._name_to_code = name_to_code
        self._code_to_name = code_to_name
        self._attr_options = list(name_to_code)

    @property
    def current_option(self) -> str | None:
        data = self.coordinator.data or {}
        return self._code_to_name.get(data.get(self._verb.lower()))

    @property
    def available(self) -> bool:
        data = self.coordinator.data or {}
        return data.get("power") == "on"

    async def async_select_option(self, option: str) -> None:
        code = self._name_to_code.get(option)
        if code is None:
            return
        try:
            await self._runtime.escvp.command(f"{self._verb} {code}", timeout=10.0)
        except EscVpError as err:
            _LOGGER.error("Setting %s=%s failed: %s", self._verb, option, err)
            return
        await self.coordinator.async_request_refresh()
