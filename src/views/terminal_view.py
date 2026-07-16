"""Terminal view — real Colab PTY shell via xterm.js.

On Android builds the terminal is rendered inside a ``flet_webview.WebView``
that loads an HTML page with xterm.js connected to the Colab TTY WebSocket.
On desktop dev (``flet run``) a button launches an external ``pywebview``
window instead (custom controls aren't available in the prebuilt desktop runner).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import flet as ft

from core import tokens
from core.theme import AppColors
from services.terminal_proxy import get_terminal_proxy_url
from services.xterm_html import create_terminal_ws_url, xterm_page

logger = logging.getLogger(__name__)

# Try to import flet_webview (only available when installed and in built apps)
try:
    import flet_webview as fwv

    WEBVIEW_AVAILABLE = True
except ImportError:
    WEBVIEW_AVAILABLE = False


def build_terminal_view(
    page: ft.Page,
    colab_service,
    state,
    session_name: str,
    on_back=None,
    snack=None,
    theme_btn=None,
) -> ft.View:
    """Build a view with the real Colab terminal."""

    _session_info = None
    _spinner_ref = ft.Ref[ft.ProgressRing]()
    _status_ref = ft.Ref[ft.Text]()

    is_mobile = page.platform.is_mobile() if page.platform else False
    can_embed = WEBVIEW_AVAILABLE and is_mobile

    # ── Status row ────────────────────────────────────────────────────────────

    status = ft.Container(
        content=ft.Row(
            controls=[
                ft.ProgressRing(ref=_spinner_ref, width=16, height=16, stroke_width=2),
                ft.Text(
                    ref=_status_ref,
                    value="Loading session…",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Container(expand=True),
            ],
            spacing=tokens.SPACE_MD,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD
        ),
    )

    # ── Helpers (defined before the layout so lambdas can capture them) ────────

    async def _launch_external(e):
        """Spawn desktop_terminal.py as a subprocess."""
        nonlocal _session_info
        try:
            _session_info = await _get_terminal_session(colab_service, session_name)
            if not _session_info:
                logger.error("Session '%s' not found in store", session_name)
                if snack:
                    snack("Session not found — create one first")
                return

            import subprocess
            import sys

            script = str(Path(__file__).resolve().parent.parent / "desktop_terminal.py")
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                script,
                "--url",
                _session_info["url"],
                "--token",
                _session_info["token"],
                "--endpoint",
                _session_info["endpoint"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                msg = f"Terminal exited with code {proc.returncode}"
                if stderr:
                    msg += f": {stderr.decode()[:500]}"
                logger.error(msg)
                if snack:
                    snack(msg)
            elif snack:
                snack("Terminal closed")
        except Exception as ex:
            if snack:
                snack(f"Error: {ex}")
            logger.exception("Failed to launch external terminal")

    # ── Body ──────────────────────────────────────────────────────────────────

    if can_embed:
        # Embedded WebView with xterm.js — this is the production path
        body = ft.Container(
            content=ft.Text("Initialising…"),
            expand=True,
            alignment=ft.Alignment.CENTER,
        )

        async def _connect_and_embed():
            nonlocal _session_info
            try:
                _session_info = await _get_terminal_session(colab_service, session_name)
                if not _session_info:
                    if _status_ref.current:
                        _status_ref.current.value = "Session not found"
                    page.update()
                    return

                colab_ws_url = await asyncio.to_thread(
                    create_terminal_ws_url, _session_info["url"], _session_info["token"]
                )
                local_ws_url = await asyncio.to_thread(
                    get_terminal_proxy_url, colab_ws_url
                )
                html = xterm_page(local_ws_url)

                webview = fwv.WebView(
                    url="about:blank",
                    expand=True,
                )

                if _status_ref.current:
                    _status_ref.current.value = ""
                if _spinner_ref.current:
                    _spinner_ref.current.visible = False

                # Replace the placeholder with the WebView
                body.content = webview
                page.update()

                # Load the xterm.js HTML into the WebView
                await webview.load_html(html)

            except Exception as ex:
                logger.error("Terminal init failed: %s", ex)
                if _status_ref.current:
                    _status_ref.current.value = f"Error: {ex}"
                    _status_ref.current.color = AppColors.ERROR
                if _spinner_ref.current:
                    _spinner_ref.current.visible = False
                page.update()

        page.run_task(_connect_and_embed)

    else:
        # Desktop dev — show a launch button for the external pywebview window
        body = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.TERMINAL_ROUNDED,
                        size=64,
                        color=ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE),
                    ),
                    ft.Container(height=tokens.SPACE_MD),
                    ft.Text(
                        "Real terminal is available when the app is built.\n"
                        "On desktop dev you can test it with pywebview.",
                        size=tokens.FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=tokens.SPACE_LG),
                    ft.FilledButton(
                        "Open Terminal (pywebview)",
                        icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                        on_click=lambda e: page.run_task(_launch_external, e),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

    # ── Layout ────────────────────────────────────────────────────────────────

    content = ft.Column(
        controls=[status, body],
        spacing=0,
        expand=True,
    )

    view = ft.View(
        route=f"/terminal?session={session_name}",
        controls=[content],
        padding=0,
        appbar=ft.AppBar(
            leading=ft.Container(
                content=ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    on_click=on_back,
                    icon_size=tokens.ICON_MD,
                    tooltip="Back",
                ),
                padding=ft.Padding(tokens.SPACE_XS, 0, 0, 0),
            ),
            leading_width=48,
            title=ft.Text("Terminal", size=tokens.FONT_LG, weight=ft.FontWeight.W_700),
            center_title=True,
            bgcolor=ft.Colors.TRANSPARENT,
            actions=[theme_btn] if theme_btn else [],
        ),
    )

    return view


# ── Shared helpers ────────────────────────────────────────────────────────────


async def _get_terminal_session(colab_service, session_name: str):
    """Retrieve endpoint, url, and token for *session_name* from Colab's store."""
    try:

        def _get():
            from colab_cli.common import State

            st = State()
            s = st.store.get(session_name)
            if not s:
                # Log available sessions to help debugging
                all_names = list(st.store.list().keys())
                logger.error(
                    "Session '%s' not found. Available: %s",
                    session_name,
                    all_names or "(none)",
                )
                return None
            return {
                "name": s.name,
                "url": s.url,
                "endpoint": s.endpoint,
                "token": s.token,
            }

        return await asyncio.to_thread(_get)
    except Exception as e:
        logger.error("Failed to get session data: %s", e)
        return None


def _build_ws_url(session: dict) -> str:
    """Construct terminal WebSocket URL by creating a terminal session via API."""
    return create_terminal_ws_url(session["url"], session["token"])
