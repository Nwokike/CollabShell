#!/usr/bin/env python3
"""Desktop terminal — standalone pywebview window with xterm.js.

Spawned as a subprocess by the Flet app on desktop (``flet run``) to provide
a real Colab terminal via a native OS window containing xterm.js.

Usage::

    python desktop_terminal.py --url https://... --token ... --endpoint m-s-...
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

# Add src to path so the shared module can be imported
_src = Path(__file__).resolve().parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from services.terminal_proxy import get_terminal_proxy_url  # noqa: E402
from services.xterm_html import create_terminal_ws_url, xterm_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("terminal")


def build_ws_url(raw_url: str, token: str) -> str:
    """Construct terminal WebSocket URL by creating a terminal session via API."""
    return create_terminal_ws_url(raw_url, token)


def test_websocket(ws_url: str, timeout: int = 10) -> bool:
    """Try connecting to the WebSocket using the Python ``websocket-client``
    library (the same one ``colab_cli.console`` uses).  Returns True if the
    connection opens within *timeout* seconds, else False."""
    import websocket

    connected = threading.Event()
    errors = []

    def on_open(ws):
        connected.set()

    def on_error(ws, err):
        errors.append(str(err))
        connected.set()  # unblock so we can report the error

    ws = websocket.WebSocketApp(ws_url, on_open=on_open, on_error=on_error)
    t = threading.Thread(
        target=ws.run_forever, kwargs={"ping_interval": 30}, daemon=True
    )
    t.start()

    ok = connected.wait(timeout=timeout)
    ws.close()
    if ok and not errors:
        logger.info("WebSocket pre-flight OK")
        return True
    logger.error("WebSocket pre-flight FAILED: %s", errors[0] if errors else "timeout")
    return False


def main():
    parser = argparse.ArgumentParser(description="Colab Terminal (pywebview)")
    parser.add_argument("--url", required=True, help="Runtime proxy base URL")
    parser.add_argument("--token", required=True, help="Runtime proxy token")
    parser.add_argument("--endpoint", required=True, help="Session endpoint ID")
    args = parser.parse_args()

    colab_ws_url = build_ws_url(args.url, args.token)
    print(f"\nRemote Colab WebSocket URL:\n{colab_ws_url}\n", flush=True)

    if not test_websocket(colab_ws_url):
        logger.warning(
            "Python WebSocket pre-flight failed (this may be an SSL/cert difference)."
        )

    # Start local proxy bridge to bypass browser Origin restrictions
    local_ws_url = get_terminal_proxy_url(colab_ws_url)
    print(f"Local Proxy WebSocket URL:\n{local_ws_url}\n", flush=True)

    # Build HTML page with xterm.js pointing to our local proxy bridge
    html = xterm_page(local_ws_url)

    try:
        import webview

        webview.create_window(
            f"Colab Terminal — {args.endpoint}",
            html=html,
            width=900,
            height=600,
            resizable=True,
        )
        webview.start(debug=True)
    except ImportError:
        logger.error(
            "pywebview is not installed. Run:  pip install pywebview qtpy PyQt6-WebEngine"
        )
        sys.exit(1)
    except Exception as e:
        logger.error("pywebview error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error("Fatal: %s", e, exc_info=True)
        sys.exit(1)
