"""Config flow for the Epson LS12000 integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

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
from .escvp21 import EscVpAuthError, EscVpClient, EscVpError
from .pjlink import PJLinkAuthError, PJLinkClient, PJLinkError

_LOGGER = logging.getLogger(__name__)


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=d.get(CONF_HOST, "")): str,
            vol.Optional(
                CONF_PJLINK_PORT, default=d.get(CONF_PJLINK_PORT, DEFAULT_PJLINK_PORT)
            ): int,
            vol.Optional(
                CONF_PJLINK_PASSWORD, default=d.get(CONF_PJLINK_PASSWORD, "")
            ): str,
            vol.Optional(
                CONF_ESCVP_PORT, default=d.get(CONF_ESCVP_PORT, DEFAULT_ESCVP_PORT)
            ): int,
            vol.Optional(
                CONF_ESCVP_PASSWORD, default=d.get(CONF_ESCVP_PASSWORD, "")
            ): str,
        }
    )


class EpsonLs12000ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the user-driven config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            errors = await _validate(user_input)
            if not errors:
                return self.async_create_entry(
                    title=f"Epson LS12000 ({user_input[CONF_HOST]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return EpsonOptionsFlow(entry)


class EpsonOptionsFlow(OptionsFlow):
    """Handle integration options (poll interval)."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._entry.options.get(
            CONF_SCAN_INTERVAL,
            self._entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    int, vol.Range(min=5, max=300)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


async def _validate(data: dict[str, Any]) -> dict[str, str]:
    """Probe both protocols. Empty dict means OK; key -> error code otherwise."""
    errors: dict[str, str] = {}
    host = data[CONF_HOST]

    # PJLink — POWR? round-trip is enough to verify auth.
    pjlink = PJLinkClient(
        host=host,
        port=data.get(CONF_PJLINK_PORT, DEFAULT_PJLINK_PORT),
        password=data.get(CONF_PJLINK_PASSWORD) or "",
    )
    try:
        await pjlink.power_query()
    except PJLinkAuthError:
        errors[CONF_PJLINK_PASSWORD] = "pjlink_auth"
    except PJLinkError as err:
        _LOGGER.debug("PJLink probe failed: %s", err)
        errors["base"] = "pjlink_unreachable"

    # ESC/VP.net — handshake + a PWR? to confirm post-CONNECT comms.
    escvp = EscVpClient(
        host=host,
        port=data.get(CONF_ESCVP_PORT, DEFAULT_ESCVP_PORT),
        password=data.get(CONF_ESCVP_PASSWORD) or "",
    )
    try:
        await escvp.async_connect()
        await escvp.command("PWR?")
    except EscVpAuthError:
        errors[CONF_ESCVP_PASSWORD] = "escvp_auth"
    except EscVpError as err:
        _LOGGER.debug("ESC/VP21 probe failed: %s", err)
        errors.setdefault("base", "escvp_unreachable")
    finally:
        await escvp.async_close()

    return errors
