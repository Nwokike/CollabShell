"""Colab — Cloud GPUs from your phone.

Main entry point following the exact same pattern as Sherlock's main.py.
"""

import logging

import flet as ft

from core import constants, tokens
from core.state import state
from core.theme import AppTheme
from core.styles import build_banner_ad
from services.colab_service import ColabService
from services.storage_service import StorageService

logger = logging.getLogger(__name__)

colab_service = ColabService()


async def main(page: ft.Page):
    page.title = constants.APP_NAME
    page.theme = AppTheme.get_light_theme()
    page.dark_theme = AppTheme.get_dark_theme()
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.padding = 0

    storage = StorageService(page)

    # ── Load saved settings from storage ──────────────────────────────────────
    theme_str = await storage.get(constants.STORAGE_THEME, "System")
    if theme_str == "Light":
        state.theme_mode = ft.ThemeMode.LIGHT
    elif theme_str == "Dark":
        state.theme_mode = ft.ThemeMode.DARK
    else:
        state.theme_mode = ft.ThemeMode.SYSTEM
    page.theme_mode = state.theme_mode

    state.auth_method = await storage.get(constants.STORAGE_AUTH_METHOD, "oauth2")
    state.default_gpu = await storage.get(constants.STORAGE_DEFAULT_GPU, "")
    state.default_tpu = await storage.get(constants.STORAGE_DEFAULT_TPU, "")
    state.default_timeout = await storage.get(constants.STORAGE_DEFAULT_TIMEOUT, 30)
    state.keep_alive_enabled = await storage.get(constants.STORAGE_KEEP_ALIVE, True)
    state.auto_stop_on_close = await storage.get(constants.STORAGE_AUTO_STOP, False)
    state.default_log_format = await storage.get(constants.STORAGE_LOG_FORMAT, "ipynb")
    state.drive_mount_path = await storage.get(constants.STORAGE_DRIVE_MOUNT_PATH, "/content/drive")
    state.logtostderr = await storage.get(constants.STORAGE_LOGTOSTDERR, False)

    # ── Init CLI service ──────────────────────────────────────────────────────
    async def _init_cli():
        try:
            await colab_service.init()
            state.cli_version = await colab_service.get_version()
            state.cli_available = True

            # Check auth
            auth_info = await colab_service.check_auth()
            state.is_authenticated = auth_info["authenticated"]
            state.auth_email = auth_info["email"]
        except Exception as e:
            logger.error("CLI init failed: %s", e)
            state.cli_available = False

    page.run_task(_init_cli)

    # ── Navigation ────────────────────────────────────────────────────────────
    def _build_nav_bar(active_index: int = 0):
        return ft.NavigationBar(
            selected_index=active_index,
            on_change=_on_nav_change,
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
        )

    def _on_nav_change(e):
        idx = e.control.selected_index
        routes = ["/home", "/history", "/settings"]
        page.go(routes[idx])

    # ── Route change handler ──────────────────────────────────────────────────
    async def route_change(e=None):
        route = page.route

        # Parse query params
        query_params = {}
        if "?" in route:
            route_base, query_str = route.split("?", 1)
            for param in query_str.split("&"):
                if "=" in param:
                    k, v = param.split("=", 1)
                    query_params[k] = v
            route = route_base

        # Clear existing views
        page.views.clear()

        # Onboarding gate
        onboarding_done = await storage.get(constants.STORAGE_ONBOARDING_DONE, False)
        if not onboarding_done and route != "/onboarding":
            page.go("/onboarding")
            return

        if route == "/onboarding":
            from views.onboarding_view import build_onboarding_view

            view_content = build_onboarding_view(
                page=page,
                colab_service=colab_service,
                state=state,
                storage=storage,
                on_complete=lambda: page.go("/home"),
            )
            page.views.append(ft.View("/onboarding", [view_content], padding=0))

        elif route == "/home":
            from views.home_view import build_home_view

            # Refresh sessions
            async def _refresh():
                try:
                    sessions = await colab_service.list_sessions(auth_method=state.auth_method)
                    state.active_sessions = sessions
                    page.update()
                except Exception as ex:
                    logger.warning("Session refresh failed: %s", ex)

            page.run_task(_refresh)

            def _on_new_session(e):
                _show_new_session_sheet()

            view_content = build_home_view(
                page=page,
                colab_service=colab_service,
                state=state,
                on_new_session=_on_new_session,
                on_session_tap=lambda name: page.go(f"/session?session={name}"),
                on_quick_run=lambda e: page.go("/run"),
                on_refresh=lambda: page.run_task(_refresh),
            )

            # AppBar with theme toggle
            app_bar = ft.AppBar(
                title=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.CLOUD_ROUNDED, color=ft.Colors.PRIMARY),
                        ft.Text(constants.APP_NAME, weight=ft.FontWeight.W_700),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                actions=[
                    ft.IconButton(
                        icon=ft.Icons.DARK_MODE_ROUNDED if state.theme_mode != ft.ThemeMode.DARK else ft.Icons.LIGHT_MODE_ROUNDED,
                        on_click=_toggle_theme,
                        tooltip="Toggle theme",
                    ),
                ],
            )

            page.views.append(
                ft.View(
                    "/home",
                    [app_bar, view_content],
                    navigation_bar=_build_nav_bar(0),
                    padding=0,
                )
            )

        elif route == "/session":
            from views.session_view import build_session_view

            session_name = query_params.get("session", "")
            view_content = build_session_view(
                page=page,
                colab_service=colab_service,
                state=state,
                session_name=session_name,
                on_back=lambda e: page.go("/home"),
            )
            page.views.append(ft.View(f"/session?session={session_name}", [view_content], padding=0))

        elif route == "/run":
            from views.run_view import build_run_view

            view_content = build_run_view(
                page=page,
                colab_service=colab_service,
                state=state,
                on_back=lambda e: page.go("/home"),
            )
            page.views.append(ft.View("/run", [view_content], padding=0))

        elif route == "/files":
            from views.files_view import build_files_view

            session_name = query_params.get("session", "")
            view_content = build_files_view(
                page=page,
                colab_service=colab_service,
                state=state,
                session_name=session_name,
                on_back=lambda e: page.go(f"/session?session={session_name}"),
            )
            page.views.append(ft.View(f"/files?session={session_name}", [view_content], padding=0))

        elif route == "/history":
            from views.history_view import build_history_view

            preselected = query_params.get("session", None)
            view_content = build_history_view(
                page=page,
                colab_service=colab_service,
                state=state,
                preselected_session=preselected,
            )

            app_bar = ft.AppBar(
                title=ft.Text("History", weight=ft.FontWeight.W_600),
                center_title=True,
            )

            page.views.append(
                ft.View(
                    "/history",
                    [app_bar, view_content],
                    navigation_bar=_build_nav_bar(1),
                    padding=0,
                )
            )

        elif route == "/settings":
            from views.settings_view import build_settings_view

            view_content = build_settings_view(
                page=page,
                colab_service=colab_service,
                state=state,
                storage=storage,
                on_theme_change=lambda: page.update(),
            )

            app_bar = ft.AppBar(
                title=ft.Text("Settings", weight=ft.FontWeight.W_600),
                center_title=True,
            )

            page.views.append(
                ft.View(
                    "/settings",
                    [app_bar, view_content],
                    navigation_bar=_build_nav_bar(2),
                    padding=0,
                )
            )

        page.update()

    # ── Theme toggle ──────────────────────────────────────────────────────────
    async def _toggle_theme(e):
        if state.theme_mode == ft.ThemeMode.DARK:
            state.theme_mode = ft.ThemeMode.LIGHT
            await storage.set(constants.STORAGE_THEME, "Light")
        else:
            state.theme_mode = ft.ThemeMode.DARK
            await storage.set(constants.STORAGE_THEME, "Dark")
        page.theme_mode = state.theme_mode
        # Rebuild the current view
        await route_change()

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

            page.close(sheet)
            state.is_provisioning = True
            page.open(ft.SnackBar(content=ft.Text("Creating session...")))
            page.update()

            try:
                result = await colab_service.new_session(
                    name=name or None,
                    gpu=gpu if gpu else None,
                    tpu=tpu if tpu else None,
                    auth_method=state.auth_method,
                )
                page.open(ft.SnackBar(content=ft.Text(f"✅ Session '{result['name']}' created!")))

                # Refresh sessions
                sessions = await colab_service.list_sessions(auth_method=state.auth_method)
                state.active_sessions = sessions
                await route_change()
            except Exception as ex:
                page.open(ft.SnackBar(content=ft.Text(f"❌ {ex}")))
            state.is_provisioning = False
            page.update()

        picker = build_hardware_picker(
            on_create=lambda e: page.run_task(_on_create, e),
            name_ref=name_ref,
            gpu_ref=gpu_ref,
            tpu_ref=tpu_ref,
        )

        sheet = ft.BottomSheet(content=picker, is_scroll_controlled=True)
        page.open(sheet)
        page.update()

    # ── Disconnect handler (auto-stop) ────────────────────────────────────────
    async def _on_disconnect(e):
        if state.auto_stop_on_close and state.active_sessions:
            for s in state.active_sessions:
                try:
                    await colab_service.stop_session(s["name"], auth_method=state.auth_method)
                except Exception:
                    pass

    page.on_disconnect = _on_disconnect

    # ── Wire up routing ───────────────────────────────────────────────────────
    page.on_route_change = lambda e: page.run_task(route_change, e)
    page.on_view_pop = lambda e: page.views.pop() if len(page.views) > 1 else None

    # ── Initial route ─────────────────────────────────────────────────────────
    page.go("/home")


ft.app(target=main)
