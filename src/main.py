"""Colab — Cloud GPUs from your phone.

Main entry point: page config, routing, service bootstrapping.
"""

from __future__ import annotations

import logging

import flet as ft

from core import constants, tokens
from core.state import state
from core.theme import AppTheme
from services.colab_service import ColabService
from services.storage_service import StorageService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("colab")

colab_service = ColabService()


async def main(page: ft.Page):
    """Main Flet application entry point."""
    page.title = constants.APP_NAME
    page.favicon = "icon.png"
    page.theme = AppTheme.get_light_theme()
    page.dark_theme = AppTheme.get_dark_theme()
    page.theme_mode = ft.ThemeMode.SYSTEM
    state.theme_mode = page.theme_mode

    page.window.min_width = 360
    page.window.min_height = 600

    page.padding = 0
    page.spacing = 0

    def on_error(e):
        logger.error("Page error: %s", e.data)
        try:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(
                    "Something went wrong. Please try again.",
                    color=ft.Colors.WHITE,
                ),
                bgcolor=ft.Colors.BLACK,
            )
            page.snack_bar.open = True
            page.update()
        except Exception:
            pass

    page.on_error = on_error

    storage = StorageService(page)

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

        auto_raw = await storage.get(constants.STORAGE_AUTO_STOP)
        if auto_raw is not None:
            state.auto_stop_on_close = auto_raw == "true"

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
            state.cli_version = await colab_service.get_version()
            state.cli_available = True

            auth_info = await colab_service.check_auth()
            state.is_authenticated = auth_info["authenticated"]
            state.auth_email = auth_info["email"]
        except Exception as e:
            logger.error("CLI init failed: %s", e)
            state.cli_available = False

    page.run_task(_init_cli)

    # ── Navigation ────────────────────────────────────────────────────────────
    async def navigate(route: str):
        page.route = route
        await route_change()

    def navigate_sync(route: str):
        page.run_task(navigate, route)

    def _snack(msg: str):
        """Show a snackbar with the given message."""
        page.snack_bar = ft.SnackBar(content=ft.Text(msg))
        page.snack_bar.open = True
        page.update()

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
    def _show_new_session_sheet():
        from components.hardware_picker import build_hardware_picker

        name_ref = ft.Ref[ft.TextField]()
        gpu_ref = ft.Ref[ft.Dropdown]()
        tpu_ref = ft.Ref[ft.Dropdown]()

        async def _on_create(e):
            name = name_ref.current.value.strip() if name_ref.current else ""
            gpu = gpu_ref.current.value if gpu_ref.current else None
            tpu = tpu_ref.current.value if tpu_ref.current else None

            page.pop_dialog()
            state.is_provisioning = True
            _snack("Creating session...")

            try:
                result = await colab_service.new_session(
                    name=name or None,
                    gpu=gpu if gpu else None,
                    tpu=tpu if tpu else None,
                    auth_method=state.auth_method,
                )
                _snack(f"✅ Session '{result['name']}' created!")

                sessions = await colab_service.list_sessions(
                    auth_method=state.auth_method,
                )
                state.active_sessions = sessions
                await route_change()
            except Exception as ex:
                _snack(f"❌ {ex}")
            state.is_provisioning = False
            page.update()

        picker = build_hardware_picker(
            on_create=lambda e: page.run_task(_on_create, e),
            name_ref=name_ref,
            gpu_ref=gpu_ref,
            tpu_ref=tpu_ref,
        )

        dialog = ft.AlertDialog(
            title=ft.Text("New Session", weight=ft.FontWeight.W_700),
            content=picker,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dialog)

    # ── Route change handler ──────────────────────────────────────────────────
    async def route_change(e=None):
        route = page.route
        logger.info("Route: %s", route)

        # Parse query params
        query_params = {}
        if "?" in route:
            route_base, query_str = route.split("?", 1)
            for param in query_str.split("&"):
                if "=" in param:
                    k, v = param.split("=", 1)
                    query_params[k] = v
            route = route_base

        page.views.clear()

        # Onboarding gate
        onboarding_done = await storage.get(constants.STORAGE_ONBOARDING_DONE)
        if onboarding_done != "true" and route != "/onboarding":
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

            async def _refresh():
                try:
                    sessions = await colab_service.list_sessions(
                        auth_method=state.auth_method,
                    )
                    state.active_sessions = sessions
                    page.update()
                except Exception as ex:
                    logger.warning("Session refresh failed: %s", ex)

            page.run_task(_refresh)

            view = build_home_view(
                page=page,
                colab_service=colab_service,
                state=state,
                on_new_session=lambda e: _show_new_session_sheet(),
                on_session_tap=lambda name: page.run_task(
                    navigate, f"/session?session={name}"
                ),
                on_quick_run=lambda e: page.run_task(navigate, "/run"),
            )
            page.views.append(view)

        elif route == "/session":
            from views.session_view import build_session_view

            session_name = query_params.get("session", "")
            view = build_session_view(
                page=page,
                colab_service=colab_service,
                state=state,
                session_name=session_name,
                on_back=lambda e: page.run_task(navigate, "/home"),
                navigate=navigate,
                snack=_snack,
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
                    navigate, f"/session?session={session_name}"
                ),
                snack=_snack,
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

            page_tags = {
                "/home": "Home",
                "/": "Home",
                "/history": "History",
                "/settings": "Settings",
            }
            tag_text = page_tags.get(route, "Colab")
            page_tag = ft.Container(
                content=ft.Text(
                    tag_text,
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.ON_SURFACE,
                ),
                padding=ft.Padding(16, 0, 0, 0),
                alignment=ft.Alignment.CENTER_LEFT,
            )

            if not top_view.appbar:
                top_view.appbar = ft.AppBar()
            top_view.appbar.leading = page_tag
            top_view.appbar.leading_width = 100
            top_view.appbar.title = ft.Row(
                [
                    ft.Image(src="icon.png", width=28, height=28),
                    ft.Text(constants.APP_NAME, weight=ft.FontWeight.W_700),
                ],
                spacing=tokens.SPACE_SM,
            )
            top_view.appbar.center_title = True
            top_view.appbar.actions = [theme_btn]
            top_view.appbar.bgcolor = ft.Colors.TRANSPARENT

        page.update()

    # ── Disconnect handler (auto-stop) ────────────────────────────────────────
    async def on_disconnect(e=None):
        if state.auto_stop_on_close and state.active_sessions:
            for s in state.active_sessions:
                try:
                    await colab_service.stop_session(
                        s["name"], auth_method=state.auth_method
                    )
                except Exception:
                    pass

    page.on_disconnect = on_disconnect

    # ── Wire up routing ───────────────────────────────────────────────────────
    page.on_route_change = route_change

    async def view_pop(e):
        page.views.pop()
        if page.views:
            top = page.views[-1]
            page.route = top.route
        page.update()

    page.on_view_pop = view_pop

    # ── Initial route ─────────────────────────────────────────────────────────
    async def _initial_route():
        onboarding_done = await storage.get(constants.STORAGE_ONBOARDING_DONE)
        if onboarding_done == "true":
            await navigate("/home")
        else:
            await navigate("/onboarding")

    page.run_task(_initial_route)


if __name__ == "__main__":
    import os

    assets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    ft.run(main, assets_dir=assets_path)
