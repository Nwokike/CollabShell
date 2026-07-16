"""Local WebSocket proxy bridge for Colab terminal.

Web browsers (including Flet WebView on Android and pywebview on Desktop) always attach an `Origin` header
when opening a WebSocket (`Origin: null` or `Origin: file://...`). Google Colab's proxy blocks any WebSocket request
that has an `Origin` header with HTTP 404 (which browsers report as WebSocket close code 1006).

This module runs a lightweight Tornado WebSocket bridge on `127.0.0.1` that:
1. Accepts WebSocket connections from the local xterm.js WebView (ignoring `Origin`).
2. Connects upstream to the Colab Jupyter terminal WebSocket (`wss://.../terminals/websocket/{name}`) without sending an `Origin` header (`Origin: None`).
3. Bridges all PTY input, output, and resize events seamlessly.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
from typing import Optional

import tornado.httpclient
import tornado.ioloop
import tornado.web
import tornado.websocket
from tornado.websocket import websocket_connect

logger = logging.getLogger(__name__)

# Global state tracking for the proxy server
_proxy_server: Optional[tornado.web.HTTPServer] = None
_proxy_port: Optional[int] = None
_proxy_thread: Optional[threading.Thread] = None
_ioloop: Optional[tornado.ioloop.IOLoop] = None
_current_colab_url: Optional[str] = None


class TerminalProxyHandler(tornado.websocket.WebSocketHandler):
    """Bridges WebSocket traffic between local xterm.js and remote Colab PTY."""

    def check_origin(self, origin: str) -> bool:
        # Allow connection from local WebView regardless of Origin (`null`, `file://`, etc.)
        return True

    async def open(self):
        colab_url = self.application.settings.get("colab_ws_url")
        if not colab_url:
            logger.error("No Colab target URL configured for proxy")
            self.close(code=1011, reason="Missing target URL")
            return

        logger.info("Local terminal client connected. Proxying upstream to Colab...")
        try:
            # Tornado HTTPRequest without Origin header matches Python websocket-client behavior
            req = tornado.httpclient.HTTPRequest(colab_url, connect_timeout=15)
            self.remote_ws = await websocket_connect(req)
            logger.info("Proxy connected upstream to Colab terminal successfully!")
            asyncio.create_task(self._forward_from_colab())
        except Exception as e:
            logger.error("Proxy failed to connect upstream to Colab terminal: %s", e)
            self.close(code=1011, reason="Upstream connection failed")

    async def _forward_from_colab(self):
        try:
            while True:
                msg = await self.remote_ws.read_message()
                if msg is None:
                    logger.info("Upstream Colab terminal WebSocket closed")
                    break
                await self.write_message(msg)
        except Exception as e:
            logger.debug("Error forwarding from Colab: %s", e)
        finally:
            self.close()

    async def on_message(self, message: str):
        if hasattr(self, "remote_ws") and self.remote_ws:
            try:
                await self.remote_ws.write_message(message)
            except Exception as e:
                logger.error("Error forwarding message upstream to Colab: %s", e)

    def on_close(self):
        logger.info("Local terminal client disconnected from proxy")
        if hasattr(self, "remote_ws") and self.remote_ws:
            self.remote_ws.close()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get_terminal_proxy_url(colab_ws_url: str) -> str:
    """Start (or reconfigure) the local Tornado WebSocket proxy bridge pointing to *colab_ws_url*
    and return the local WebSocket URL (`ws://127.0.0.1:<port>/`) for the WebView to connect to.
    """
    global _proxy_server, _proxy_port, _proxy_thread, _ioloop, _current_colab_url

    if _proxy_server is not None and _proxy_port is not None and _ioloop is not None:
        # Update target if proxy is already running
        _current_colab_url = colab_ws_url
        if _proxy_server.request_callback.settings.get("colab_ws_url") != colab_ws_url:
            _proxy_server.request_callback.settings["colab_ws_url"] = colab_ws_url
            logger.info("Updated existing proxy server target to: %s", colab_ws_url)
        return f"ws://127.0.0.1:{_proxy_port}/"

    port = _find_free_port()
    _proxy_port = port
    _current_colab_url = colab_ws_url

    app = tornado.web.Application(
        [(r"/", TerminalProxyHandler)],
        colab_ws_url=colab_ws_url,
    )

    started_event = threading.Event()

    def _run():
        global _proxy_server, _ioloop
        # Create a fresh IOLoop for this background thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _ioloop = tornado.ioloop.IOLoop.current()

        _proxy_server = app.listen(port, address="127.0.0.1")
        logger.info("Started local terminal proxy server on ws://127.0.0.1:%s/", port)
        started_event.set()

        try:
            _ioloop.start()
        except Exception as e:
            logger.error("Terminal proxy IOLoop exited: %s", e)

    _proxy_thread = threading.Thread(
        target=_run, name="TerminalProxyThread", daemon=True
    )
    _proxy_thread.start()
    started_event.wait(timeout=5)

    return f"ws://127.0.0.1:{port}/"
