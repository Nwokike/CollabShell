"""Colab PTY Terminal WebSocket Client.

Connects directly from Python to the Google Colab Jupyter terminal WebSocket
(`wss://.../terminals/websocket/{name}?colab-runtime-proxy-token={token}`),
bypassing browser Origin header restrictions and eliminating the need for local proxies.
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


def create_terminal_ws_url(raw_url: str, token: str) -> str:
    """Create a new PTY terminal session via POST /api/terminals on the Colab server
    and return the corresponding WebSocket URL (`wss://.../terminals/websocket/{name}`).
    """
    base_url = raw_url.rstrip("/")
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
    ):
        self.ws_url = ws_url
        self.on_stdout = on_stdout
        self.on_status = on_status
        self.ws: WebSocketClientConnection | None = None
        self._running = False
        self._read_task: asyncio.Task | None = None

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
            if self.on_status:
                self.on_status(f"Connection error: {e}", False)
            self._running = False
            raise

    async def _read_loop(self):
        """Continuously read messages from Colab and push stdout to the terminal."""
        try:
            while self._running and self.ws:
                msg = await self.ws.read_message()
                if msg is None:
                    logger.info("Upstream Colab terminal WebSocket closed by server.")
                    if self.on_status:
                        self.on_status("Disconnected by server", False)
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
        except Exception as e:
            if self._running:
                logger.error("Error reading from Colab terminal WebSocket: %s", e)
                if self.on_status:
                    self.on_status(f"Error: {e}", False)
        finally:
            self.close()

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
        """Cleanly close the WebSocket connection and stop the read loop."""
        self._running = False
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        logger.info("Colab terminal client closed.")
