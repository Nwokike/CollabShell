"""Colab PTY Terminal WebSocket Client.

Connects directly from Python to the Google Colab Jupyter terminal WebSocket
(`wss://.../terminals/websocket/{name}?colab-runtime-proxy-token={token}`),
bypassing browser Origin header restrictions and eliminating the need for local proxies.

The client caches the created PTY name plus the raw URL/token used to build its
WebSocket URL, so it can re-attach to the SAME still-alive PTY after a drop
(app backgrounded, network blip, Colab's idle-proxy closing the socket). A
read-timeout watchdog probes the upstream and auto-reconnects dead sockets.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from urllib.parse import urlparse

import requests
import tornado.httpclient
from tornado.websocket import WebSocketClientConnection, websocket_connect

logger = logging.getLogger(__name__)

# Colab's WS proxy closes sockets that stay quiet. Wake up on this interval to
# either detect a dead socket or ping the upstream so it stays open.
WS_PING_INTERVAL = 10
PING_PAYLOAD = b"colabshell-ping"


def create_terminal_ws_url(
    raw_url: str, token: str, term_name: str | None = None
) -> str:
    """Return the WebSocket URL for a Colab PTY terminal.

    With no `term_name`, a new PTY is created via `POST /api/terminals`. With a
    `term_name`, the URL for the existing PTY is returned without creating a
    new one — this is how a dropped connection re-attaches instead of minting
    a brand-new shell.
    """
    base_url = raw_url.rstrip("/")

    if term_name is None:
        post_url = f"{base_url}/api/terminals?colab-runtime-proxy-token={token}"
        headers = {
            "X-Colab-Runtime-Proxy-Token": token,
        }

        logger.info("Creating PTY terminal via POST %s", post_url)
        resp = requests.post(post_url, headers=headers, timeout=10)
        resp.raise_for_status()

        term_info = resp.json()
        term_name = term_info["name"]
        logger.info("Created Colab terminal '%s'", term_name)

    parsed = urlparse(base_url)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = (
        f"{ws_scheme}://{parsed.netloc}/terminals/websocket/{term_name}"
        f"?colab-runtime-proxy-token={token}"
    )
    return ws_url


class ColabTerminalClient:
    """Direct upstream WebSocket client for Google Colab PTY terminals."""

    def __init__(
        self,
        ws_url: str,
        on_stdout: Callable[[str], None],
        on_status: Callable[[str, bool], None] | None = None,
        base_url: str | None = None,
        token: str | None = None,
        term_name: str | None = None,
        session_name: str | None = None,
    ):
        self.ws_url = ws_url
        self.on_stdout = on_stdout
        self.on_status = on_status
        # Reconnect support: cached so we can re-attach to the same PTY.
        self.base_url = base_url
        self.token = token
        self.term_name = term_name
        # Session record name — lets reconnects pick up a re-minted
        # runtime-proxy token (the cached one expires after hours).
        self.session_name = session_name
        self.ws: WebSocketClientConnection | None = None
        self._running = False
        self._abandoned = False
        self._reconnecting = False
        self._read_task: asyncio.Task | None = None

    async def _refresh_cached_credentials(self) -> bool:
        """Re-read this session's url/token from the local store.

        list_sessions/refresh_session_token heal the stored record when the
        short-lived runtime-proxy JWT expires; a long-lived client must
        re-read it before rebuilding its WS URL or it keeps presenting the
        stale token (every reconnect 404s). Returns True when the cached
        credentials changed.
        """
        if not self.session_name:
            return False

        def _read():
            from colab_cli.common import State

            s = State().store.get(self.session_name)
            if not s:
                return None
            return (s.url, s.token)

        try:
            creds = await asyncio.to_thread(_read)
        except Exception:
            logger.debug(
                "credential re-read failed for %s",
                self.session_name,
                exc_info=True,
            )
            return False
        if creds is None:
            return False
        url, token = creds
        if url == self.base_url and token == self.token:
            return False
        self.base_url = url
        self.token = token
        logger.info(
            "Terminal client picked up refreshed runtime proxy token (%s).",
            self.session_name,
        )
        return True

    @property
    def alive(self) -> bool:
        return self._running and self.ws is not None

    async def connect(self, initial_rows: int = 24, initial_cols: int = 80):
        """Connect to the remote Colab terminal WebSocket."""
        self._running = True
        if self.on_status:
            self.on_status("Connecting to Colab terminal…", False)

        try:
            req = tornado.httpclient.HTTPRequest(
                self.ws_url,
                connect_timeout=15,
            )
            self.ws = await websocket_connect(req)
            logger.info("Direct WebSocket connected upstream to Colab terminal.")
            if self.on_status:
                self.on_status("Connected", True)

            # Send initial size
            await self.set_size(initial_rows, initial_cols)

            # Start reading loop
            self._read_task = asyncio.create_task(self._read_loop())
        except Exception as e:
            logger.error("Failed to connect to Colab terminal WebSocket: %s", e)
            self.ws = None
            if self.on_status:
                self.on_status(f"Connection error: {e}", False)
            self._running = False
            raise

    async def _read_loop(self):
        """Continuously read messages from Colab and push stdout to the terminal.

        Reads use a timeout rather than an unbounded await: after quiet
        periods the socket may be dead without signaling a close (typical when
        the app was backgrounded), so the timeout lets us probe and reconnect.
        """
        my_ws = self.ws
        while self._running and self.ws is my_ws and my_ws is not None:
            try:
                msg = await asyncio.wait_for(
                    my_ws.read_message(), timeout=WS_PING_INTERVAL
                )
            except TimeoutError:
                if not self._probe_upstream():
                    logger.warning(
                        "Terminal upstream looks dead after idle — reconnecting"
                    )
                    await asyncio.to_thread(my_ws.close)
                    break
                continue
            except Exception as e:
                if self._running:
                    logger.error("Error reading from Colab terminal WebSocket: %s", e)
                    if self.on_status:
                        self.on_status(f"Error: {e}", False)
                break

            if msg is None:
                logger.info("Upstream Colab terminal WebSocket closed by server.")
                break

            try:
                m = json.loads(msg)
                if isinstance(m, list):
                    if m[0] == "stdout" and len(m) > 1:
                        logger.debug(
                            "Received Colab stdout chunk (%d chars)", len(m[1])
                        )
                        self.on_stdout(m[1])
                    elif m[0] == "setup":
                        logger.info("Colab TTY setup complete.")
                        asyncio.create_task(self.set_size(24, 80))
                    elif m[0] == "disconnect":
                        logger.warning("Colab TTY disconnected by server.")
                        if self.on_status:
                            self.on_status("Disconnected", False)
                elif isinstance(m, dict) and "data" in m:
                    logger.debug(
                        "Received Colab dict data chunk (%d chars)", len(m["data"])
                    )
                    self.on_stdout(m["data"])
            except Exception as ex:
                logger.error(
                    "Error parsing terminal WebSocket message: %s - payload: %s",
                    ex,
                    msg,
                )

        wanted_to_run = self._running and not self._abandoned
        self._teardown_socket()
        if wanted_to_run:
            # Unexpected drop while still running — re-attach to the PTY.
            asyncio.create_task(self._reconnect_with_backoff())

    def _probe_upstream(self) -> bool:
        """Return True when the WS accepts an app-level ping (socket alive)."""
        try:
            if self.ws is None:
                return False
            self.ws.ping(PING_PAYLOAD)
            return True
        except Exception:
            return False

    async def _reconnect_with_backoff(
        self, max_attempts: int = 12, base_delay: float = 1.0
    ):
        """Re-attach to our PTY with exponential backoff (1s → ~15s cap).

        Colab's PTY outlives the WebSocket hop, so reattaching by name
        restores the same shell (cwd, env, history intact) — no fresh PTY is
        minted. If the PTY itself is gone (session stopped/recycled), stop
        retrying and report instead of creating a surprise new shell.
        """
        if not self.base_url or not self.token or not self.term_name:
            logger.error("Terminal reconnect impossible: no cached session info")
            if self.on_status:
                self.on_status("Disconnected", False)
            return
        if self._reconnecting:
            return  # manual reconnect() is already handling it
        self._reconnecting = True
        try:
            await self._reconnect_attempts(max_attempts, base_delay)
        finally:
            self._reconnecting = False

    async def _reconnect_attempts(self, max_attempts: int, base_delay: float):
        for attempt in range(1, max_attempts + 1):
            delay = min(base_delay * (2 ** (attempt - 1)), 15.0)
            if self.on_status:
                self.on_status(f"Reconnecting… (attempt {attempt})", False)
            await asyncio.sleep(delay)

            if self._abandoned:
                return  # Panel was closed or replaced this client meanwhile.

            try:
                await self._refresh_cached_credentials()
                self.ws_url = await asyncio.to_thread(
                    create_terminal_ws_url,
                    self.base_url,
                    self.token,
                    self.term_name,
                )
                await self.connect()
                logger.info(
                    "Terminal '%s' reconnected after %d attempt(s).",
                    self.term_name,
                    attempt,
                )
                return
            except Exception as ex:
                status = getattr(getattr(ex, "response", None), "status_code", None)
                logger.warning(
                    "Terminal reconnect attempt %d/%d failed: %s%s",
                    attempt,
                    max_attempts,
                    ex,
                    f" (HTTP {status})" if status is not None else "",
                )
                # Permanent 4xx (e.g. 404 terminal gone) — stop hammering.
                if status is not None and 400 <= status < 500:
                    break

        self._running = False
        logger.error(
            "Terminal '%s' reconnect failed after retries — giving up.",
            self.term_name,
        )
        if self.on_status:
            self.on_status("Disconnected — could not reconnect", False)

    async def reconnect(self) -> bool:
        """Re-attach to the cached PTY now (called on app resume)."""
        if self.alive:
            return True
        if self._reconnecting:
            return True  # a backoff loop is already working on it
        if not self.base_url or not self.token or not self.term_name:
            return False
        self._reconnecting = True
        try:
            self._abandoned = False
            self._running = False
            await self._refresh_cached_credentials()
            self.ws_url = await asyncio.to_thread(
                create_terminal_ws_url, self.base_url, self.token, self.term_name
            )
            await self.connect()
            logger.info("Terminal '%s' resumed with fresh connection.", self.term_name)
            return True
        except Exception as ex:
            logger.warning("Manual terminal reconnect failed: %s", ex)
            return False
        finally:
            self._reconnecting = False

    async def send_input(self, data: str | bytes):
        """Send user keystrokes to Colab PTY (`["stdin", text]`)."""
        if not self.ws or not self._running:
            return
        try:
            payload = (
                data if isinstance(data, str) else data.decode("utf-8", errors="ignore")
            )
            msg = json.dumps(["stdin", payload])
            await self.ws.write_message(msg)
            logger.debug(
                "Sent stdin to Colab (%d chars): %s", len(payload), repr(payload)
            )
        except Exception as e:
            logger.error("Failed to send terminal input: %s", e)

    async def set_size(self, rows: int, cols: int):
        """Notify Colab PTY of terminal window dimension changes (`["set_size", rows, cols]`)."""
        if not self.ws or not self._running:
            return
        try:
            msg = json.dumps(["set_size", rows, cols])
            await self.ws.write_message(msg)
            logger.debug("Sent resize to Colab: rows=%s, cols=%s", rows, cols)
        except Exception as e:
            logger.error("Failed to send terminal resize: %s", e)

    def close(self):
        """Permanently close the client: no reconnect attempts will follow."""
        self._abandoned = True
        self._teardown_socket()
        logger.info("Colab terminal client closed.")

    def _teardown_socket(self):
        """Stop the read loop and close the socket (reconnect may follow)."""
        self._running = False
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                logger.exception("Suppressed exception")
            self.ws = None
