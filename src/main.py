"""Colab — Cloud GPUs from your phone.

Main entry point: page config, routing, service bootstrapping.
"""

from __future__ import annotations

import asyncio
import atexit
import logging

from core.storage_patch import apply_storage_patches

apply_storage_patches()

import flet as ft

from core import constants
from core.state import state
from core.theme import AppTheme
from services.ad_service import AdService
from services.colab import ColabService
from services.storage_service import StorageService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from core.storage_patch import _memory_log_handler

for log_name in ["", "colab", "flet", "router", "services", "core",
                  "colab_service", "colab_session_ops", "colab_auth"]:
    lg = logging.getLogger(log_name)
    if _memory_log_handler not in lg.handlers:
        lg.addHandler(_memory_log_handler)
    # Ensure they actually pass INFO logs down
    if lg.level == logging.NOTSET:
        lg.setLevel(logging.INFO)
    # Ensure propagation doesn't duplicate if we attach to both child and root
    if log_name != "":
        lg.propagate = False

logger = logging.getLogger("colab")

colab_service = ColabService()


async def main(page: ft.Page):
    """Main Flet application entry point."""
    page.fonts = {
        "Outfit": "assets/fonts/Outfit-Regular.ttf",
        "RobotoMono": "assets/fonts/RobotoMono-Regular.ttf",
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
                    # Persist until dismissed so a transient glitch doesn't hide
                    # the message before the user can read it.
                    persist=True,
                    show_close_icon=True,
                )
            )
        except Exception:
            pass

    page.on_error = on_error

    storage = StorageService(page)
    ad_service = AdService(page)
    state.ad_service = ad_service
    await ad_service.gather_consent()
    page.run_task(ad_service.preload_interstitial)

    # Native connectivity monitoring (flet 0.86.5 ft.Connectivity). Replaces the
    # hand-rolled DNS-probe polling loop with a reactive on_change event.
    def _on_connectivity_change(e):
        is_online = ft.ConnectivityType.NONE not in e.connectivity
        state.is_online = is_online
        # Keep the /home offline banner reactive without a periodic poll.
        if page.route == "/home":
            page.run_task(navigate, "/home")

    state.connectivity = ft.Connectivity(on_change=_on_connectivity_change)
    page.services.append(state.connectivity)

    file_picker = ft.FilePicker()
    page.services.append(file_picker)
    page.file_picker = file_picker

    from core.stdin_hook import setup_global_stdin_hook

    setup_global_stdin_hook(page, colab_service, lambda m: _snack(m))

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
            state.logtostderr = str(log_raw).lower() == "true"
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
        """Show a snackbar with the given message.

        FLOATING so it hovers above the bottom NavigationBar instead of
        shoving it; swipe-up to dismiss.
        """
        page.show_dialog(
            ft.SnackBar(
                content=ft.Text(msg),
                behavior=ft.SnackBarBehavior.FLOATING,
                dismiss_direction=ft.DismissDirection.UP,
            )
        )

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
    def _show_new_session_sheet(mode=None, ignore_warning=False):
        from components.new_session_sheet import show_new_session_sheet

        show_new_session_sheet(
            page=page,
            state=state,
            colab_service=colab_service,
            ad_service=ad_service,
            navigate=navigate,
            route_change=route_change,
            snack_func=_snack,
            mode=mode,
            ignore_warning=ignore_warning,
        )

    # ── Route change handler ──────────────────────────────────────────────────

    async def route_change(e=None):
        from core.router import route_change_impl

        await route_change_impl(
            page=page,
            colab_service=colab_service,
            state=state,
            storage=storage,
            navigate=navigate,
            show_new_session_sheet=_show_new_session_sheet,
            snack=_snack,
        )

    # ── Disconnect handler (auto-stop) ────────────────────────────────────────
    def _cleanup_sessions():
        """Stop all sessions synchronously (used by atexit)."""
        if state.keep_alive_on_disconnect or not state.active_sessions:
            return
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            for s in state.active_sessions:
                name = s.get("name")
                if not name:
                    continue
                try:
                    loop.run_until_complete(
                        colab_service.stop_session(name, auth_method=state.auth_method)
                    )
                except Exception as exc:
                    logger.warning("Cleanup failed for session %s: %s", name, exc)
            loop.close()
        except Exception as e:
            logger.warning("atexit cleanup encountered error: %s", e)

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

    # ── Android / mobile lifecycle ────────────────────────────────────────────
    # Android suspends/kills backgrounded apps, which kills asyncio tasks.
    # When the user brings the app back to the foreground (RESUMED), we:
    #   1. Re-probe connectivity so the offline banner updates immediately.
    #   2. Restart any keep-alive tasks that died while suspended.
    # NOTE: We cannot keep Python alive while Android has killed the process;
    # this handler only helps when the OS *suspended* (not killed) the app.
    async def _on_lifecycle_change(e: ft.AppLifecycleStateChangeEvent):
        if e.state != ft.AppLifecycleState.RESUMED:
            return

        logger.info("[lifecycle] app resumed — re-probing connectivity")

        # 1. Re-probe connectivity
        try:
            connectivity = await state.connectivity.get_connectivity()
            state.is_online = ft.ConnectivityType.NONE not in connectivity
        except Exception as exc:
            logger.warning("[lifecycle] connectivity probe failed: %s", exc)

        # 2. Restart dead keep-alive tasks
        if state.is_online and state.active_sessions:
            dead = [
                name
                for name, task in colab_service._keep_alive_tasks.items()
                if task.done()
            ]
            for session_name in dead:
                # Look up endpoint from active_sessions list
                ep = next(
                    (
                        s.get("endpoint")
                        for s in state.active_sessions
                        if s.get("name") == session_name
                    ),
                    None,
                )
                if ep:
                    logger.info(
                        "[lifecycle] restarting keep-alive for %s", session_name
                    )
                    colab_service._start_in_process_keep_alive(
                        session_name, ep, state.auth_method
                    )

        # 3. Refresh the current view so the offline banner is up-to-date
        if page.route == "/home":
            page.run_task(navigate, "/home")

    page.on_app_lifecycle_state_change = _on_lifecycle_change

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
        # Probe connectivity first. If offline, surface the offline screen and
        # skip auth entirely — a returning user must not be forced back through
        # onboarding just because the token can't be refreshed right now.
        connectivity = await state.connectivity.get_connectivity()
        state.is_online = ft.ConnectivityType.NONE not in connectivity
        if not state.is_online:
            await navigate("/offline")
            return

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

    # Public alias so the offline screen's Retry can re-enter routing.
    async def run_initial_route():
        await _initial_route()

    page.run_task(_initial_route)


if __name__ == "__main__":
    import os

    assets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    ft.run(main, assets_dir=assets_path)
