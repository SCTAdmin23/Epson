"""The Epson LS12000 integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ESCVP_PASSWORD,
    CONF_ESCVP_PORT,
    CONF_PJLINK_PASSWORD,
    CONF_PJLINK_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_ESCVP_PORT,
    DEFAULT_PJLINK_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import EpsonCoordinator
from .escvp21 import EscVpClient
from .pjlink import PJLinkClient, PJLinkError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.MEDIA_PLAYER,
    Platform.REMOTE,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.BUTTON,
]


@dataclass
class EpsonRuntimeData:
    """Runtime objects for a configured projector."""

    coordinator: EpsonCoordinator
    escvp: EscVpClient
    pjlink: PJLinkClient

    async def power(self, on: bool) -> None:
        """Turn the projector on or off using whichever protocol responds.

        PJLink is tried first because it works in deep standby with no
        session setup, while the ESC/VP.net listener on port 3629 may not
        accept connections (or may stall the CONNECT handshake) until the
        projector finishes waking. ESC/VP21 is the fallback for projectors
        where PJLink is disabled or password-mismatched.
        """
        try:
            if on:
                await self.pjlink.power_on()
            else:
                await self.pjlink.power_off()
            return
        except PJLinkError as err:
            _LOGGER.debug(
                "PJLink power_%s failed (%s); falling back to ESC/VP21",
                "on" if on else "off",
                err,
            )
        await self.escvp.command("PWR ON" if on else "PWR OFF", timeout=60.0)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Epson LS12000 from a config entry."""
    host = entry.data[CONF_HOST]
    escvp = EscVpClient(
        host=host,
        port=entry.data.get(CONF_ESCVP_PORT, DEFAULT_ESCVP_PORT),
        password=entry.data.get(CONF_ESCVP_PASSWORD) or "",
    )
    pjlink = PJLinkClient(
        host=host,
        port=entry.data.get(CONF_PJLINK_PORT, DEFAULT_PJLINK_PORT),
        password=entry.data.get(CONF_PJLINK_PASSWORD) or "",
    )

    # No prewarm. The coordinator's first refresh opens the ESC/VP21 socket
    # only when the projector is reachable, and the coordinator falls back
    # to PJLink for power state when ESC/VP21 is unavailable (e.g., the
    # projector is in deep standby and the listener on 3629 hasn't woken).

    coordinator = EpsonCoordinator(
        hass,
        host=host,
        escvp=escvp,
        pjlink=pjlink,
        scan_interval=entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = EpsonRuntimeData(
        coordinator=coordinator, escvp=escvp, pjlink=pjlink
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear down a configured projector."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime: EpsonRuntimeData = hass.data[DOMAIN].pop(entry.entry_id)
        await runtime.escvp.async_close()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change (e.g. poll interval)."""
    await hass.config_entries.async_reload(entry.entry_id)
