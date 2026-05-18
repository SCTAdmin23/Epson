"""Shared base entity for Epson LS12000 entities."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import EpsonCoordinator


class EpsonEntity(CoordinatorEntity[EpsonCoordinator]):
    """Base class wiring DeviceInfo + unique_id namespace."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EpsonCoordinator, suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.host}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.host)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=f"Epson LS12000 ({coordinator.host})",
            configuration_url=f"http://{coordinator.host}/",
        )
