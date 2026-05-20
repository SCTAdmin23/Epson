"""DataUpdateCoordinator for the Epson LS12000 integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, PWR_STATE
from .escvp21 import EscVpClient, EscVpCommandError, EscVpError
from .pjlink import PJLinkClient, PJLinkError

# PJLink POWR? response codes (JBMIA spec).
_PJLINK_POWR = {"0": "standby", "1": "on", "2": "cooldown", "3": "warmup"}

_LOGGER = logging.getLogger(__name__)

# Commands we poll while the projector is on. PWR is always polled; the rest
# only when PWR=='on' to avoid ERR responses in standby/warmup/cooldown.
_ON_STATE_QUERIES: tuple[str, ...] = (
    "SOURCE?",
    "CMODE?",
    "ASPECT?",
    "DYNRANGE?",
    "CLRSPACE?",
    "MCFI?",
    "LUMLEVEL?",
    "IMGPRESET?",
)


class EpsonCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the projector via ESC/VP21 with PJLink as the auth-fallback for power."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        escvp: EscVpClient,
        pjlink: PJLinkClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{host}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.host = host
        self.escvp = escvp
        self.pjlink = pjlink

    async def _async_update_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {}

        # Power state comes from PJLink first — it works in every projector
        # power state (including deep standby) with a fresh per-command socket,
        # while ESC/VP.net on port 3629 can stall its handshake or refuse
        # connections until the projector is fully awake. We only fall back to
        # ESC/VP21's PWR? if PJLink itself errors out (port closed, password
        # mismatch, network down).
        try:
            pjlink_raw = await self.pjlink.power_query()
            data["power"] = _PJLINK_POWR.get(pjlink_raw, "unknown")
        except (PJLinkError, asyncio.TimeoutError, TimeoutError, OSError) as pjerr:
            _LOGGER.debug("PJLink power_query failed (%s); trying ESC/VP21", pjerr)
            try:
                pwr_code = await self.escvp.command("PWR?")
            except (EscVpError, asyncio.TimeoutError, TimeoutError, OSError) as err:
                raise UpdateFailed(
                    f"PJLink and ESC/VP21 both failed: {pjerr}; {err}"
                ) from err
            data["power_code"] = pwr_code
            data["power"] = PWR_STATE.get(pwr_code, "unknown")

        if data["power"] != "on":
            return data

        # Probe the rest. No single failure should kill the whole poll — we
        # already have a valid power state, which is what entity availability
        # hinges on. Log transient issues and move on.
        for query in _ON_STATE_QUERIES:
            try:
                value = await self.escvp.command(query)
            except EscVpCommandError as err:
                _LOGGER.debug("Projector returned ERR for %s: %s", query, err)
                continue
            except (EscVpError, asyncio.TimeoutError, TimeoutError, OSError) as err:
                _LOGGER.debug("Transient failure on %s: %s", query, err)
                continue
            key = query.rstrip("?").lower()
            data[key] = value

        return data
