"""Async ESC/VP.net + ESC/VP21 client for Epson projectors.

Implements the binary CONNECT handshake from the ESC/VP.net Software Development
Manual (rev F), then exchanges ASCII ESC/VP21 commands on the same TCP socket.

Wire format (16-byte common header, §5.4.1):
    'ESC/VP.net' (10B) | 0x10 ver | type | seq:2B=0 | status | nheaders

Header (18B, §5.4.2):
    id:1B | attr:1B | data:16B STR (0x00-padded)

CONNECT (type=3) with Password header (id=1, attr=1 Plain) on §5.6.3.
Response status codes: 0x20 OK, 0x41 Unauthorized, 0x43 Forbidden,
0x53 Service Unavailable, 0x55 Protocol Version Not Supported.

After 0x20, the socket carries raw ESC/VP21. Each command:
    "<CMD> <PARAM>\\r" or "<CMD>?\\r" -> server replies with "<CMD>=<val>\\r"
    for queries, then a trailing ':' once the projector is idle.
Set commands return only ':'. Bad commands return 'ERR\\r:'.
Idle timeout is 10 min (§5.6.1); we send a bare '\\r' keepalive every 4 min.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Final

from .const import ESCVP_TIMEOUT

_LOGGER = logging.getLogger(__name__)

_MAGIC: Final = b"ESC/VP.net"
_VERSION: Final = 0x10
_TYPE_HELLO: Final = 1
_TYPE_PASSWORD: Final = 2
_TYPE_CONNECT: Final = 3

_HDR_PASSWORD: Final = 1
_HDR_ATTR_NULL: Final = 0
_HDR_ATTR_PLAIN: Final = 1

_STATUS_OK: Final = 0x20
_STATUS_BAD_REQUEST: Final = 0x40
_STATUS_UNAUTHORIZED: Final = 0x41
_STATUS_FORBIDDEN: Final = 0x43
_STATUS_NOT_ALLOWED: Final = 0x45
_STATUS_BUSY: Final = 0x53
_STATUS_BAD_VERSION: Final = 0x55

# Idle ping interval (server enforces 10-min cutoff per §5.6.1).
_KEEPALIVE_INTERVAL: Final = 240.0

# Handshake timeout — longer than per-command because the projector's
# ESC/VP.net listener takes its time to respond to CONNECT when the unit is
# in standby (Standby Mode: Communication On still goes through a wake-up).
_HANDSHAKE_TIMEOUT: Final = 15.0


class EscVpError(Exception):
    """Base error from the ESC/VP21 client."""


class EscVpAuthError(EscVpError):
    """Projector rejected the password (status 0x43)."""


class EscVpBusyError(EscVpError):
    """Projector is busy or cannot start a new session (status 0x53)."""


class EscVpCommandError(EscVpError):
    """Projector returned 'ERR' for an ESC/VP21 command."""


def _build_common(type_id: int, status: int, nheaders: int) -> bytes:
    return _MAGIC + bytes([_VERSION, type_id, 0, 0, status, nheaders])


def _build_password_header(password: str) -> bytes:
    if not password:
        return bytes([_HDR_PASSWORD, _HDR_ATTR_NULL]) + b"\x00" * 16
    data = password.encode("ascii")
    if len(data) > 16:
        raise EscVpError("ESC/VP.net password must be 16 ASCII chars or fewer")
    data = data.ljust(16, b"\x00")
    return bytes([_HDR_PASSWORD, _HDR_ATTR_PLAIN]) + data


def _close_writer(writer: asyncio.StreamWriter) -> None:
    """Close a writer and ignore any teardown errors."""
    try:
        writer.close()
    except Exception:  # noqa: BLE001
        pass


def _parse_common(buf: bytes) -> tuple[int, int, int]:
    """Return (type_id, status, nheaders) from a 16-byte common header."""
    if len(buf) < 16 or not buf.startswith(_MAGIC):
        raise EscVpError(f"Invalid ESC/VP.net response prefix: {buf!r}")
    type_id = buf[11]
    status = buf[14]
    nheaders = buf[15]
    return type_id, status, nheaders


class EscVpClient:
    """Persistent ESC/VP.net session with single-flight command queue."""

    def __init__(self, host: str, port: int, password: str | None) -> None:
        self._host = host
        self._port = port
        self._password = password or ""
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._keepalive_task: asyncio.Task[None] | None = None

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def async_connect(self) -> None:
        """Open the TCP socket and run the CONNECT handshake."""
        async with self._lock:
            await self._open_locked()

    async def async_close(self) -> None:
        async with self._lock:
            await self._close_locked()

    async def _open_locked(self) -> None:
        if self.connected:
            return
        reader, writer = await self._dial_and_handshake()
        self._reader = reader
        self._writer = writer
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def _close_locked(self) -> None:
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._keepalive_task = None
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
        self._reader = None
        self._writer = None

    async def _dial_and_handshake(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Open TCP and run CONNECT; retry once with password on Unauthorized."""
        # If we have a password, send it on the first try — the LS12000 will
        # ignore it when no password is set on the projector (§5.7), and this
        # avoids a wasted round-trip + reconnect when one is set.
        attempt_password = self._password or None
        for attempt in (1, 2):
            reader, writer = await asyncio.open_connection(self._host, self._port)
            try:
                await self._send_connect(writer, password=attempt_password)
                status = await self._read_connect_response(reader)
            except Exception:
                _close_writer(writer)
                raise

            if status == _STATUS_OK:
                return reader, writer

            _close_writer(writer)

            if status == _STATUS_UNAUTHORIZED and attempt == 1 and self._password:
                # Should not happen since we sent password, but spec allows the
                # server to demand a retry — try once more with credentials.
                attempt_password = self._password
                continue
            if status == _STATUS_UNAUTHORIZED:
                raise EscVpAuthError(
                    "Projector requires an ESC/VP.net password"
                )
            if status == _STATUS_FORBIDDEN:
                raise EscVpAuthError("ESC/VP.net password rejected")
            if status == _STATUS_BUSY:
                raise EscVpBusyError("Projector busy; cannot start session")
            raise EscVpError(
                f"ESC/VP.net CONNECT failed with status 0x{status:02X}"
            )
        raise EscVpError("Unreachable")

    async def _send_connect(
        self, writer: asyncio.StreamWriter, *, password: str | None
    ) -> None:
        if password is None or password == "":
            packet = _build_common(_TYPE_CONNECT, 0x00, 0)
        else:
            packet = _build_common(_TYPE_CONNECT, 0x00, 1) + _build_password_header(
                password
            )
        writer.write(packet)
        await writer.drain()

    async def _read_connect_response(self, reader: asyncio.StreamReader) -> int:
        header = await asyncio.wait_for(
            reader.readexactly(16), timeout=_HANDSHAKE_TIMEOUT
        )
        type_id, status, nheaders = _parse_common(header)
        if type_id != _TYPE_CONNECT:
            raise EscVpError(
                f"Unexpected response type {type_id} (expected CONNECT)"
            )
        if nheaders:
            await asyncio.wait_for(
                reader.readexactly(18 * nheaders), timeout=_HANDSHAKE_TIMEOUT
            )
        return status

    async def _keepalive_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(_KEEPALIVE_INTERVAL)
                try:
                    async with self._lock:
                        if not self.connected:
                            return
                        await self._send_raw_locked(b"\r")
                        await self._read_until_prompt_locked()
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Keepalive failed: %s; dropping session", err)
                    # Drop the socket inline so the next user command sees
                    # `connected == False` and goes through a full reconnect.
                    # We deliberately do NOT call _close_locked() here because
                    # it would await this very task and deadlock.
                    async with self._lock:
                        if self._writer is not None:
                            _close_writer(self._writer)
                        self._reader = None
                        self._writer = None
                    return
        except asyncio.CancelledError:
            return

    # ------------------------------------------------------------------ commands

    async def command(self, body: str, *, timeout: float = ESCVP_TIMEOUT) -> str:
        """Send an ESC/VP21 command and return the value (or '' for sets).

        For queries ('FOO?'), returns the right side of 'FOO=<val>'.
        For sets, returns ''.
        Raises EscVpCommandError when the projector returns 'ERR'.
        Reconnects transparently if the socket has dropped or stalled.
        """
        async with self._lock:
            for attempt in (1, 2):
                try:
                    if not self.connected:
                        await self._open_locked()
                    return await asyncio.wait_for(
                        self._exchange_locked(body), timeout=timeout
                    )
                except (EscVpAuthError, EscVpCommandError):
                    # Auth and ERR responses are not transient — don't retry.
                    raise
                except (
                    EscVpError,
                    ConnectionError,
                    asyncio.IncompleteReadError,
                    asyncio.TimeoutError,
                    TimeoutError,
                    OSError,
                ) as err:
                    _LOGGER.debug(
                        "ESC/VP21 transport failed on %r (%s); reconnect", body, err
                    )
                    await self._close_locked()
                    if attempt == 2:
                        raise EscVpError(
                            f"ESC/VP21 transport failed for {body!r}: {err}"
                        ) from err
            raise EscVpError("Unreachable")

    async def _exchange_locked(self, body: str) -> str:
        assert self._reader is not None
        assert self._writer is not None
        await self._send_raw_locked(body.encode("ascii") + b"\r")

        # Reads end at the colon prompt ':' which the projector emits after
        # a command completes. For queries the value line precedes the colon.
        buf = b""
        value = ""
        while True:
            chunk = await self._reader.read(256)
            if not chunk:
                raise ConnectionError("ESC/VP21 socket closed mid-read")
            buf += chunk
            if b":" in buf:
                before, _, rest = buf.partition(b":")
                # Anything after the colon belongs to a subsequent reply; for
                # single-flight use we should never see it, but discard safely.
                for line in before.split(b"\r"):
                    line = line.strip()
                    if not line:
                        continue
                    text = line.decode("ascii", errors="replace")
                    if text == "ERR":
                        raise EscVpCommandError(f"Projector returned ERR for {body!r}")
                    if "=" in text:
                        value = text.split("=", 1)[1].strip()
                # If we somehow buffered ahead, push the leftover back.
                if rest:
                    # readuntil()-style pushback is awkward on StreamReader; in
                    # practice the projector never speaks ahead, so we just log.
                    _LOGGER.debug("Trailing bytes after prompt discarded: %r", rest)
                return value

    async def _send_raw_locked(self, data: bytes) -> None:
        assert self._writer is not None
        self._writer.write(data)
        await self._writer.drain()

    async def _read_until_prompt_locked(self) -> bytes:
        assert self._reader is not None
        buf = b""
        while b":" not in buf:
            chunk = await self._reader.read(256)
            if not chunk:
                raise ConnectionError("ESC/VP21 socket closed mid-read")
            buf += chunk
        return buf
