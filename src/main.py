# ruff: noqa: E402
"""Colab — Cloud GPUs from your phone.

Main entry point: page config, routing, service bootstrapping.
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import time

from core.storage_patch import apply_storage_patches

apply_storage_patches()

import flet as ft

from core import constants, tokens
from core.state import state
from core.theme import AppTheme
from services.colab_service import ColabService
from services.storage_service import StorageService
from services.ad_service import AdService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("colab")

colab_service = ColabService()


async def main(page: ft.Page):
    """Main Flet application entry point."""
    page.fonts = {
        "Outfit": "assets/outfit.css",
        "RobotoMono": "assets/roboto_mono.css",
    }
    page.title = constants.APP_NAME
    page.favicon = "icon.png"
    page.theme = AppTheme.get_light_theme()
    page.dark_theme = AppTheme.get_dark_theme()
    page.theme_mode = ft.ThemeMode.SYSTEM
    state.theme_mode = page.theme_mode

    page.padding = 0
    page.spacing = 0

    def on_error(e):
        logger.error("Page error: %s", e.data)
        try:
            page.show_dialog(
                ft.SnackBar(
                    content=ft.Text(
                        "Something went wrong. Please try again.",
                        color=ft.Colors.WHITE,
                    ),
                    bgcolor=ft.Colors.BLACK,
                )
            )
        except Exception:
            pass

    page.on_error = on_error

    storage = StorageService(page)
    ad_service = AdService(page)
    state.ad_service = ad_service
    page.run_task(ad_service.preload_interstitial)

    file_picker = ft.FilePicker()
    page.services.append(file_picker)
    page.file_picker = file_picker

    # ── Load saved settings ───────────────────────────────────────────────────
    try:
        theme_str = await storage.get(constants.STORAGE_THEME)
        if theme_str == "dark":
            page.theme_mode = ft.ThemeMode.DARK
        elif theme_str == "light":
            page.theme_mode = ft.ThemeMode.LIGHT
        else:
            page.theme_mode = ft.ThemeMode.SYSTEM
        state.theme_mode = page.theme_mode

        auth_raw = await storage.get(constants.STORAGE_AUTH_METHOD)
        state.auth_method = auth_raw if auth_raw else "oauth2"

        gpu_raw = await storage.get(constants.STORAGE_DEFAULT_GPU)
        state.default_gpu = gpu_raw if gpu_raw else ""

        tpu_raw = await storage.get(constants.STORAGE_DEFAULT_TPU)
        state.default_tpu = tpu_raw if tpu_raw else ""

        timeout_raw = await storage.get(constants.STORAGE_DEFAULT_TIMEOUT)
        if timeout_raw:
            state.default_timeout = int(timeout_raw)

        keep_raw = await storage.get(constants.STORAGE_KEEP_ALIVE)
        if keep_raw is not None:
            state.keep_alive_enabled = keep_raw == "true"

        disconnect_raw = await storage.get(constants.STORAGE_KEEP_ALIVE_ON_DISCONNECT)
        if disconnect_raw is not None:
            state.keep_alive_on_disconnect = disconnect_raw == "true"

        fmt_raw = await storage.get(constants.STORAGE_LOG_FORMAT)
        state.default_log_format = fmt_raw if fmt_raw else "ipynb"

        drive_raw = await storage.get(constants.STORAGE_DRIVE_MOUNT_PATH)
        state.drive_mount_path = drive_raw if drive_raw else "/content/drive"

        log_raw = await storage.get(constants.STORAGE_LOGTOSTDERR)
        if log_raw is not None:
            state.logtostderr = log_raw == "true"
    except Exception as e:
        logger.warning("Settings load failed: %s", e)

    # ── Init CLI service ──────────────────────────────────────────────────────
    async def _init_cli():
        try:
            await colab_service.init()
            state.cli_available = True

            auth_info = await colab_service.check_auth()
            state.is_authenticated = auth_info["authenticated"]
            state.auth_email = auth_info["email"]
        except Exception as e:
            logger.error("CLI init failed: %s", e)
            state.cli_available = False

    # ── Navigation ────────────────────────────────────────────────────────────
    async def navigate(route: str):
        page.route = route
        await route_change()

    def navigate_sync(route: str):
        page.run_task(navigate, route)

    def _snack(msg: str):
        """Show a snackbar with the given message."""
        page.show_dialog(ft.SnackBar(content=ft.Text(msg)))

    def _build_nav_bar(active_route: str):
        routes = ["/home", "/history", "/settings"]
        nav_bar = ft.NavigationBar(
            selected_index=routes.index(active_route) if active_route in routes else 0,
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.HOME_OUTLINED,
                    selected_icon=ft.Icons.HOME_ROUNDED,
                    label=constants.LBL_HOME,
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.HISTORY_OUTLINED,
                    selected_icon=ft.Icons.HISTORY_ROUNDED,
                    label=constants.LBL_HISTORY,
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS_ROUNDED,
                    label=constants.LBL_SETTINGS,
                ),
            ],
            bgcolor=ft.Colors.SURFACE,
            indicator_color=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
            label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        )

        def on_nav_change(e):
            index = e.control.selected_index
            page.run_task(navigate, routes[index])

        nav_bar.on_change = on_nav_change
        return nav_bar

    # ── New Session Sheet ─────────────────────────────────────────────────────
    def _show_new_session_sheet(ignore_warning=False):
        def _close_limit_dialog(e=None):
            limit_dialog.open = False
            page.update()
            
        def _on_proceed(e):
            _close_limit_dialog()
            _show_new_session_sheet(ignore_warning=True)

        if not ignore_warning and len(state.active_sessions) >= 3:
            limit_dialog = ft.AlertDialog(
                title=ft.Text("Session Limit", weight=ft.FontWeight.BOLD),
                content=ft.Text(
                    "You already have 3 active sessions. Creating another session might fail with a quota error unless you have a Google Colab Pro subscription.\n\nDo you want to proceed?"
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=_close_limit_dialog),
                    ft.TextButton("Proceed", on_click=_on_proceed),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.show_dialog(limit_dialog)
            return

        from components.hardware_picker import build_hardware_picker

        name_ref = ft.Ref[ft.TextField]()
        gpu_ref = ft.Ref[ft.Dropdown]()
        tpu_ref = ft.Ref[ft.Dropdown]()
        hardware_type_ref = ft.Ref[ft.SegmentedButton]()

        async def _on_create(e):
            name = name_ref.current.value.strip() if name_ref.current else ""

            # Read hardware selection
            selected_hw = (
                list(hardware_type_ref.current.selected)[0]
                if hardware_type_ref.current and hardware_type_ref.current.selected
                else "CPU"
            )

            gpu = (
                gpu_ref.current.value
                if (gpu_ref.current and selected_hw == "GPU")
                else None
            )
            tpu = (
                tpu_ref.current.value
                if (tpu_ref.current and selected_hw == "TPU")
                else None
            )

            paid_gpus = {"L4", "G4", "A100", "H100"}
            if gpu in paid_gpus:
                def _close_confirm(data):
                    confirm_dialog.data = data
                    confirm_dialog.open = False
                    page.update()

                confirm_dialog = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Paid Accelerator Selected"),
                    content=ft.Text(
                        f"{gpu} requires Colab Pro or Pay As You Go and may incur charges. Continue?"
                    ),
                    actions=[
                        ft.TextButton(
                            "Cancel",
                            on_click=lambda e: _close_confirm("cancel"),
                        ),
                        ft.FilledButton(
                            "Continue",
                            on_click=lambda e: _close_confirm("continue"),
                        ),
                    ],
                )
                page.show_dialog(confirm_dialog)
                # Wait for user to make a choice
                while getattr(confirm_dialog, "data", None) is None:
                    await asyncio.sleep(0.1)
                if confirm_dialog.data == "cancel":
                    return

            hw_dialog.open = False
            page.update()
            await ad_service.show_interstitial()

            loading_dialog = ft.AlertDialog(
                modal=True,
                content=ft.Container(
                    content=ft.Row(
                        [
                            ft.ProgressRing(
                                width=24,
                                height=24,
                                stroke_width=3,
                            ),
                            ft.Text(
                                "Creating session...",
                                size=tokens.FONT_SM,
                                weight=ft.FontWeight.W_500,
                            ),
                        ],
                        spacing=12,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_XL,
                        tokens.SPACE_LG,
                        tokens.SPACE_XL,
                        tokens.SPACE_LG,
                    ),
                ),
            )
            page.show_dialog(loading_dialog)
            state.is_provisioning = True

            try:
                logger.info(
                    "Attempting to create session: %s (GPU=%s, TPU=%s)", name, gpu, tpu
                )
                result = await colab_service.new_session(
                    name=name or None,
                    gpu=gpu if gpu else None,
                    tpu=tpu if tpu else None,
                    auth_method=state.auth_method,
                    keep_alive=state.keep_alive_enabled,
                )
                logger.info("Session created successfully: %s", result)
                loading_dialog.open = False
                page.update()

                _snack(f"✅ Session '{result['name']}' created!")

                sessions = await colab_service.list_sessions(
                    auth_method=state.auth_method,
                )
                state.active_sessions = sessions
                await route_change()
            except Exception as ex:
                logger.error(f"Failed to create session: {ex}", exc_info=True)
                loading_dialog.open = False
                page.update()
                _snack(f"❌ {ex}")
            state.is_provisioning = False
            page.update()

        picker = build_hardware_picker(
            on_create=lambda e: page.run_task(_on_create, e),
            name_ref=name_ref,
            gpu_ref=gpu_ref,
            tpu_ref=tpu_ref,
            hardware_type_ref=hardware_type_ref,
        )

        hw_dialog = ft.AlertDialog(
            title=ft.Text("New Session", weight=ft.FontWeight.W_700),
            content=picker,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(hw_dialog)

    # ── Route change handler ──────────────────────────────────────────────────
    import urllib.parse

    async def route_change(e=None):
        page.views.clear()
        route = page.route
        parsed = urllib.parse.urlparse(route)
        route = parsed.path
        query_params = dict(urllib.parse.parse_qsl(parsed.query))

        async def _global_toggle_theme(e=None):
            is_dark = page.theme_mode == ft.ThemeMode.DARK or (
                page.theme_mode == ft.ThemeMode.SYSTEM
                and page.platform_brightness == ft.Brightness.DARK
            )
            page.theme_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
            state.theme_mode = page.theme_mode
            await storage.set(
                constants.STORAGE_THEME,
                "light" if page.theme_mode == ft.ThemeMode.LIGHT else "dark",
            )
            theme_btn.icon = (
                ft.Icons.LIGHT_MODE_ROUNDED
                if page.theme_mode == ft.ThemeMode.DARK
                else ft.Icons.DARK_MODE_ROUNDED
            )
            page.update()

        theme_btn = ft.IconButton(
            icon=ft.Icons.LIGHT_MODE_ROUNDED
            if page.theme_mode == ft.ThemeMode.DARK
            else ft.Icons.DARK_MODE_ROUNDED,
            tooltip="Toggle Theme",
            on_click=lambda e: page.run_task(_global_toggle_theme),
        )
        logger.info("Route: %s", route)

        page.views.clear()

        # Onboarding gate
        if not state.onboarding_done and route != "/onboarding":
            page.route = "/onboarding"
            await route_change()
            return

        if route == "/onboarding":
            from views.onboarding_view import build_onboarding_view

            view = build_onboarding_view(
                page=page,
                colab_service=colab_service,
                state=state,
                storage=storage,
                on_complete=lambda: page.run_task(navigate, "/home"),
                snack=_snack,
            )
            page.views.append(view)

        elif route == "/home" or route == "/":
            from views.home_view import build_home_view

            view = build_home_view(
                page=page,
                colab_service=colab_service,
                state=state,
                on_new_session=lambda e: _show_new_session_sheet(),
                on_session_tap=lambda name: page.run_task(
                    navigate, f"/session?session={name}"
                ),
                navigate=navigate,
                on_refresh=lambda e: page.run_task(
                    colab_service.list_sessions, "oauth2"
                ),
                storage=storage,
            )
            page.views.append(view)

        elif route == "/session":
            from views.session_view import build_session_view

            session_name = query_params.get("session", "")
            initial_tab = query_params.get("tab", "notebook")

            view = build_session_view(
                page=page,
                colab_service=colab_service,
                state=state,
                session_name=session_name,
                initial_tab=initial_tab,
                on_back=lambda e: page.run_task(navigate, "/home"),
                navigate=navigate,
                snack=_snack,
                theme_btn=theme_btn,
                storage=storage,
            )
            page.views.append(view)

        elif route == "/run":
            from views.run_view import build_run_view

            view = build_run_view(
                page=page,
                colab_service=colab_service,
                state=state,
                on_back=lambda e: page.run_task(navigate, "/home"),
                snack=_snack,
                theme_btn=theme_btn,
            )
            page.views.append(view)

        elif route == "/files":
            from views.files_view import build_files_view

            session_name = query_params.get("session", "")
            view = build_files_view(
                page=page,
                colab_service=colab_service,
                state=state,
                session_name=session_name,
                on_back=lambda e: page.run_task(
                    navigate, f"/session?session={urllib.parse.quote(session_name)}"
                ),
                snack=_snack,
                theme_btn=theme_btn,
            )
            page.views.append(view)

        elif route == "/terminal":
            from views.terminal_view import build_terminal_view

            session_name = query_params.get("session", "")
            view = build_terminal_view(
                page=page,
                colab_service=colab_service,
                state=state,
                session_name=session_name,
                on_back=lambda e: page.run_task(
                    navigate, f"/session?session={session_name}"
                ),
                snack=_snack,
                theme_btn=theme_btn,
            )
            page.views.append(view)

        elif route == "/history":
            from views.history_view import build_history_view

            preselected = query_params.get("session", None)
            view = build_history_view(
                page=page,
                colab_service=colab_service,
                state=state,
                preselected_session=preselected,
                snack=_snack,
                theme_btn=theme_btn,
            )
            page.views.append(view)

        elif route == "/settings":
            from views.settings_view import build_settings_view

            view = build_settings_view(
                page=page,
                colab_service=colab_service,
                state=state,
                storage=storage,
            )
            page.views.append(view)

        else:
            page.route = "/home"
            await route_change()
            return

        # Attach nav bar to tabbed views
        if page.views and route in ("/home", "/", "/history", "/settings"):
            page.views[-1].navigation_bar = _build_nav_bar(route)

        # Attach appbar to tabbed views
        if page.views and route in ("/home", "/", "/history", "/settings"):
            top_view = page.views[-1]

            # Define root routes that get the custom Page Tag leading widget
            root_routes = {"/home", "/", "/history", "/settings"}

            if route in root_routes:
                page_tags = {
                    "/home": "Home",
                    "/": "Home",
                    "/history": "History",
                    "/settings": "Settings",
                }
                tag_text = page_tags.get(route, "Collab Shell")

                page_tag = ft.Container(
                    content=ft.Text(
                        tag_text,
                        size=tokens.FONT_LG,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.ON_SURFACE,
                    ),
                    padding=ft.Padding(tokens.SPACE_LG, 0, 0, 0),
                    alignment=ft.Alignment.CENTER_LEFT,
                )

                if not top_view.appbar:
                    top_view.appbar = ft.AppBar()
                top_view.appbar.leading = page_tag
                top_view.appbar.leading_width = 100
                top_view.appbar.title = ft.Container()
                top_view.appbar.center_title = True
                top_view.appbar.actions = [theme_btn]
                top_view.appbar.bgcolor = ft.Colors.TRANSPARENT
            else:
                # Sub-views handle their own appbars natively
                pass

        page.update()

    # ── Disconnect handler (auto-stop) ────────────────────────────────────────
    def _cleanup_sessions():
        """Stop all sessions synchronously (used by atexit)."""
        if state.keep_alive_on_disconnect or not state.active_sessions:
            return
        for s in state.active_sessions:
            try:
                name = s.get("name")
                if not name:
                    continue
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    colab_service.stop_session(name, auth_method=state.auth_method)
                )
                loop.close()
            except Exception as exc:
                logger.warning("Cleanup failed for session %s: %s", s.get("name"), exc)
            time.sleep(0.5)

    atexit.register(_cleanup_sessions)

    async def on_disconnect(e=None):
        if state.keep_alive_on_disconnect or not state.active_sessions:
            return
        for s in state.active_sessions:
            name = s.get("name")
            if not name:
                continue
            try:
                await colab_service.stop_session(name, auth_method=state.auth_method)
            except Exception as exc:
                logger.warning("Disconnect cleanup failed for %s: %s", name, exc)

    page.on_disconnect = on_disconnect

    # ── Wire up routing ───────────────────────────────────────────────────────
    # Navigation is driven explicitly via navigate()/route_change() (which set
    # page.route and rebuild views). We deliberately do NOT register
    # on_route_change: assigning page.route already fires the route-change
    # event, so registering it would cause every navigation to run twice.
    page.on_route_change = None

    async def view_pop(e):
        page.views.pop()
        if page.views:
            top = page.views[-1]
            page.route = top.route
        else:
            page.route = "/home"
        await route_change()

    page.on_view_pop = view_pop

    # ── Initial route ─────────────────────────────────────────────────────────
    async def _initial_route():
        await _init_cli()
        if state.is_authenticated:
            state.onboarding_done = True
            await storage.set(constants.STORAGE_ONBOARDING_DONE, "true")
        else:
            onboarding_done = await storage.get(constants.STORAGE_ONBOARDING_DONE)
            state.onboarding_done = onboarding_done == "true"

        if state.onboarding_done and state.is_authenticated:
            await navigate("/home")
        else:
            await navigate("/onboarding")

    page.run_task(_initial_route)


if __name__ == "__main__":
    import os

    assets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    ft.run(main, assets_dir=assets_path)
