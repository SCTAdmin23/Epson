"""Async PJLink Class 1 client with MD5 challenge-response auth.

Protocol summary (JBMIA PJLink spec):
  Connect TCP/4352. Server greets with one of:
    PJLINK 0\r          -> no auth
    PJLINK 1 <8hex>\r   -> auth; prefix every command with md5(nonce+password)
  Each command: %1<CMD> <PARAM>\r  -> response: %1<CMD>=<VAL>\r
  Errors: ERR1 undefined / ERR2 bad param / ERR3 unavailable / ERR4 failure /
          ERRA auth failure.

The connection is single-shot per command (PJLink projectors typically close
the socket after each response). The LS12000 follows this pattern.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Final

from .const import PJLINK_TIMEOUT

_LOGGER = logging.getLogger(__name__)

_GREETING_PREFIX: Final = b"PJLINK"
_ERR_AUTH: Final = "ERRA"


class PJLinkError(Exception):
    """Base error from the PJLink client."""


class PJLinkAuthError(PJLinkError):
    """Raised when the projector rejects the password."""


class PJLinkClient:
    """Stateless PJLink client; one connection per command."""

    def __init__(self, host: str, port: int, password: str | None) -> None:
        self._host = host
        self._port = port
        self._password = password or ""
        self._lock = asyncio.Lock()

    async def command(self, body: str, *, timeout: float = PJLINK_TIMEOUT) -> str:
        """Send a command body (e.g. "POWR ?") and return the value portion of the reply.

        Returns the part after "=" for queries, or "OK" for accepted set commands.
        Raises PJLinkAuthError on auth failure, PJLinkError for other ERR responses.
        """
        async with self._lock:
            return await asyncio.wait_for(self._exchange(body), timeout=timeout)

    async def _exchange(self, body: str) -> str:
        reader, writer = await asyncio.open_connection(self._host, self._port)
        try:
            greeting = await reader.readuntil(b"\r")
            prefix = b""
            if greeting.startswith(b"PJLINK 1 "):
                nonce = greeting[len(b"PJLINK 1 ") : -1].decode("ascii")
                digest = hashlib.md5(  # noqa: S324 - PJLink protocol requires MD5
                    (nonce + self._password).encode("ascii")
                ).hexdigest()
                prefix = digest.encode("ascii")
            elif not greeting.startswith(b"PJLINK 0"):
                raise PJLinkError(f"Unexpected greeting: {greeting!r}")

            writer.write(prefix + b"%1" + body.encode("ascii") + b"\r")
            await writer.drain()

            reply = await reader.readuntil(b"\r")
            text = reply.decode("ascii", errors="replace").rstrip("\r")

            if text == _ERR_AUTH:
                raise PJLinkAuthError("PJLink authentication failed")

            # Response format: %1CMD=VALUE
            if "=" not in text:
                raise PJLinkError(f"Malformed PJLink reply: {text}")
            value = text.split("=", 1)[1]
            if value.startswith("ERR"):
                raise PJLinkError(f"PJLink error {value} for command {body!r}")
            return value
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001 - best-effort close
                pass

    async def power_query(self) -> str:
        """Return PJLink POWR status: 0=off, 1=on, 2=cooling, 3=warmup."""
        return await self.command("POWR ?")

    async def power_on(self) -> None:
        await self.command("POWR 1")

    async def power_off(self) -> None:
        await self.command("POWR 0")

    async def input_query(self) -> str:
        """Return INPT code, e.g. '31' for HDMI1."""
        return await self.command("INPT ?")

    async def input_set(self, code: str) -> None:
        await self.command(f"INPT {code}")

    async def mute_query(self) -> str:
        """Return AVMT code: 11 video mute on, 21 audio mute on, 31 both on, x0 off."""
        return await self.command("AVMT ?")

    async def name_query(self) -> str:
        return await self.command("NAME ?")

    async def info1_query(self) -> str:
        """Manufacturer name."""
        return await self.command("INF1 ?")

    async def info2_query(self) -> str:
        """Product name."""
        return await self.command("INF2 ?")

    async def error_query(self) -> str:
        """6-digit error status: fan/lamp/temp/cover/filter/other, 0=ok 1=warn 2=err."""
        return await self.command("ERST ?")
