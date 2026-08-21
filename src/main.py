"""Colab Shell — Unofficial mobile and desktop client for Google Colab.

Main entry point: Bootstraps services and mounts the React-like component tree via page.render().
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import sys

import flet as ft

from core.storage_patch import apply_storage_patches

apply_storage_patches()

from app_shell import AppShell
from components.new_session_sheet import show_new_session_sheet
from core import constants, tokens
from core.notifications import show_notification
from core.state import state
from core.stdin_hook import setup_global_stdin_hook
from core.storage_patch import _memory_log_handler
from core.theme import AppTheme
from services.ad_service import AdService
from services.colab import ColabService
from services.storage_service import StorageService
from state import ControllerMethods, ControllerMethodsCtx, ServiceCtx, Services

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

log_fmt = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Ensure stdout handler is attached to root
has_stream = any(
    isinstance(h, logging.StreamHandler)
    and not isinstance(h, type(_memory_log_handler))
    for h in root_logger.handlers
)
if not has_stream:
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(log_fmt)
    stdout_handler.setLevel(logging.INFO)
    root_logger.addHandler(stdout_handler)

# Attach memory log handler to root so all logs are captured for History/Logs view
if _memory_log_handler not in root_logger.handlers:
    root_logger.addHandler(_memory_log_handler)

logging.captureWarnings(True)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("flet_controls").setLevel(logging.WARNING)

logger = logging.getLogger("colab")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class AppController:
    """Initializes backend services, handles lifecycle events, and mounts the AppShell."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.storage: StorageService | None = None
        self.ad_service: AdService | None = None
        self.colab_service: ColabService | None = None

    async def init(self):
        """Bootstrap services, restore preferences, and render the application."""
        page = self.page

        # ── Window & Typography ───────────────────────────────────────────────
        page.title = constants.APP_NAME
        page.fonts = {
            "Outfit": "assets/fonts/Outfit-Regular.ttf",
            "RobotoMono": "assets/fonts/RobotoMono-Regular.ttf",
        }
        page.theme = AppTheme.get_light_theme()
        page.dark_theme = AppTheme.get_dark_theme()
        page.theme.font_family = "Outfit"
        page.dark_theme.font_family = "Outfit"
        page.theme_mode = ft.ThemeMode.SYSTEM
        state.theme_mode = page.theme_mode

        page.window.min_width = tokens.WINDOW_MIN_WIDTH
        page.window.min_height = tokens.WINDOW_MIN_HEIGHT
        page.padding = 0
        page.spacing = 0

        loop = asyncio.get_running_loop()

        def _async_exception_handler(l, context):
            exc = context.get("exception")
            msg = context.get("message", "Unhandled async exception")
            logger.error("Unhandled async exception: %s", msg, exc_info=exc)

        loop.set_exception_handler(_async_exception_handler)

        page.on_error = self._on_error

        def _on_platform_brightness(e):
            # In SYSTEM mode the host OS can flip light/dark at runtime. Bump the
            # observable revision so adaptive (hardcoded-hex) surfaces re-render;
            # the client re-themes all semantic-token colors automatically.
            state.theme_revision += 1
            page.update()

        page.on_platform_brightness_change = _on_platform_brightness

        # ── Global Services ───────────────────────────────────────────────────
        file_picker = ft.FilePicker()
        page.services.append(file_picker)
        page.file_picker = file_picker

        connectivity = ft.Connectivity()
        page.services.append(connectivity)
        page.connectivity = connectivity
        state.connectivity = connectivity

        def _on_connectivity_change(e):
            try:
                types = getattr(e, "connectivity", None) or [e.data]
                state.is_online = ft.ConnectivityType.NONE not in types
            except Exception:
                state.is_online = True
            page.update()

        connectivity.on_change = _on_connectivity_change

        self.storage = StorageService(page)
        self.ad_service = AdService(page)
        state.ad_service = self.ad_service
        await self.ad_service.gather_consent()
        page.run_task(self.ad_service.preload_interstitial)

        self.colab_service = ColabService()

        async def _init_cli():
            try:
                await self.colab_service.init()
                state.cli_available = self.colab_service.is_available
                # Keep the CLI's own logging in sync with the app preference
                cli_state = getattr(self.colab_service, "_cli_state", None)
                if cli_state is not None:
                    cli_state.logtostderr = state.logtostderr
            except Exception as ex:
                logger.warning("CLI init failed: %s", ex)
                state.cli_available = False

        page.run_task(_init_cli)

        # Global stdin fallback for kernel prompts outside notebook cells
        setup_global_stdin_hook(
            page, self.colab_service, lambda m: show_notification(page, m)
        )

        # ── Restore Preferences ───────────────────────────────────────────────
        await self._restore_preferences()

        # Apply the restored log-to-stderr preference immediately
        from core.storage_patch import set_log_to_stderr

        set_log_to_stderr(state.logtostderr)

        # ── Routing (deep links + internal navigation share one entry point) ──
        import urllib.parse

        _TAB_ROUTES = {
            "/": 0,
            "/home": 0,
            "/notebooks_tab": 1,
            "/terminals_tab": 2,
            "/files_tab": 3,
            "/settings": 4,
        }
        _TAB_ROUTE_NAMES = [
            "/home",
            "/notebooks_tab",
            "/terminals_tab",
            "/files_tab",
            "/settings",
        ]

        def _apply_route(route: str):
            """Map a route string onto app state. Idempotent — safe to run
            twice, so it serves both page.on_route_change (deep links,
            system back) and direct internal navigation."""
            try:
                parsed = urllib.parse.urlparse(route)
                path = parsed.path or "/"
                query = dict(urllib.parse.parse_qsl(parsed.query))
            except Exception:
                path, query = route or "/", {}

            if path in _TAB_ROUTES:
                state.active_subview = ""
                state.active_session_name = ""
                state.current_tab = _TAB_ROUTES[path]
                return
            if path == "/session":
                name = query.get("session", "")
                if name:
                    state.active_session_name = name
                    state.session_mode = (
                        "terminal" if query.get("tab") == "terminal" else "notebook"
                    )
                    state.active_subview = "session"
                return
            if path == "/terminal":
                name = query.get("session", "")
                if name:
                    state.active_session_name = name
                    state.session_mode = "terminal"
                    state.active_subview = "session"
                return
            if path == "/files":
                name = query.get("session", "")
                if name:
                    state.active_session_name = name
                    state.session_mode = "files"
                    state.active_subview = "session"
                return
            if path == "/history":
                state.selected_session_name = query.get("session", "")
                state.active_subview = "history"
                return
            # /onboarding, /offline and unknown routes fall back to home;
            # the shell's state gates decide what actually renders.
            state.active_subview = ""
            state.active_session_name = ""
            state.current_tab = 0

        def _navigate(route: str):
            _apply_route(route)
            try:
                page.route = route
            except Exception:
                logger.exception("Suppressed exception")

        # Expose for handlers registered in other methods (e.g. on_view_pop).
        self._navigate = _navigate

        def _on_route_change(e):
            _apply_route(getattr(e, "route", "/"))

        page.on_route_change = _on_route_change

        # ── Controller Methods for UI ─────────────────────────────────────────
        def _show_snack(msg: str, is_error: bool = False, is_warning: bool = False):
            show_notification(page, msg, is_error=is_error, is_warning=is_warning)

        def _navigate_tab(idx: int):
            if 0 <= idx < len(_TAB_ROUTE_NAMES):
                _navigate(_TAB_ROUTE_NAMES[idx])

        def _open_session(name: str, mode: str = "notebook"):
            encoded = urllib.parse.quote(name)
            if mode == "files":
                _navigate(f"/files?session={encoded}")
            elif mode == "terminal":
                _navigate(f"/terminal?session={encoded}")
            else:
                _navigate(f"/session?session={encoded}")

        def _close_session():
            _navigate("/home")

        def _open_history(session_name: str = ""):
            if session_name:
                _navigate(f"/history?session={urllib.parse.quote(session_name)}")
            else:
                _navigate("/history")

        def _close_history():
            _navigate("/home")

        def _show_new_session_sheet(mode: str = "notebook"):
            show_new_session_sheet(
                page=page,
                state=state,
                colab_service=self.colab_service,
                ad_service=self.ad_service,
                on_session_created=lambda name: _open_session(name, mode),
                snack_func=_show_snack,
                mode=mode,
                ignore_warning=False,
            )

        def _toggle_theme():
            if page.theme_mode == ft.ThemeMode.SYSTEM:
                page.theme_mode = ft.ThemeMode.LIGHT
            elif page.theme_mode == ft.ThemeMode.LIGHT:
                page.theme_mode = ft.ThemeMode.DARK
            else:
                page.theme_mode = ft.ThemeMode.SYSTEM
            state.theme_mode = page.theme_mode
            theme_val = "system"
            if page.theme_mode == ft.ThemeMode.LIGHT:
                theme_val = "light"
            elif page.theme_mode == ft.ThemeMode.DARK:
                theme_val = "dark"
            page.run_task(
                self.storage.set,
                constants.STORAGE_THEME,
                theme_val,
            )
            page.update()

        methods = ControllerMethods(
            navigate_tab=_navigate_tab,
            open_session=_open_session,
            close_session=_close_session,
            open_history=_open_history,
            close_history=_close_history,
            show_snack=_show_snack,
            show_new_session_sheet=_show_new_session_sheet,
            toggle_theme=_toggle_theme,
        )

        services = Services(
            colab=self.colab_service,
            storage=self.storage,
            ad_service=self.ad_service,
            page=page,
        )

        # ── Register Lifecycle & Disconnect Handlers ──────────────────────────
        self._register_lifecycle_handlers()

        # ── Mount Reactive Component Tree ─────────────────────────────────────
        page.render(
            lambda: ServiceCtx(
                services,
                lambda: ControllerMethodsCtx(
                    methods,
                    lambda: AppShell(),
                ),
            )
        )
        logger.info("Colab Shell application mounted successfully")

        # ── Initial background bootstrap (auth, connectivity, sessions) ──────
        page.run_task(self._bootstrap_state)

    async def _restore_preferences(self):
        try:
            saved_theme = await self.storage.get(constants.STORAGE_THEME)
            theme_map = {
                "dark": ft.ThemeMode.DARK,
                "system": ft.ThemeMode.SYSTEM,
                "light": ft.ThemeMode.LIGHT,
            }
            if saved_theme in theme_map:
                self.page.theme_mode = theme_map[saved_theme]
                state.theme_mode = self.page.theme_mode

            saved_keep_alive = await self.storage.get(constants.STORAGE_KEEP_ALIVE)
            if saved_keep_alive is not None:
                state.keep_alive_enabled = saved_keep_alive == "true"

            saved_keep_alive_dc = await self.storage.get(
                constants.STORAGE_KEEP_ALIVE_ON_DISCONNECT
            )
            if saved_keep_alive_dc is not None:
                state.keep_alive_on_disconnect = saved_keep_alive_dc == "true"

            saved_gpu = await self.storage.get(constants.STORAGE_DEFAULT_GPU)
            if saved_gpu:
                state.default_gpu = saved_gpu

            saved_tpu = await self.storage.get(constants.STORAGE_DEFAULT_TPU)
            if saved_tpu:
                state.default_tpu = saved_tpu

            saved_timeout = await self.storage.get(constants.STORAGE_DEFAULT_TIMEOUT)
            if saved_timeout:
                try:
                    state.default_timeout = int(saved_timeout)
                except ValueError:
                    pass

            saved_drive_path = await self.storage.get(
                constants.STORAGE_DRIVE_MOUNT_PATH
            )
            if saved_drive_path:
                state.drive_mount_path = saved_drive_path

            saved_logtostderr = await self.storage.get(constants.STORAGE_LOGTOSTDERR)
            if saved_logtostderr is not None:
                state.logtostderr = saved_logtostderr == "true"
            else:
                state.logtostderr = True
        except Exception as e:
            logger.warning("Failed to restore some preferences: %s", e)

    async def _bootstrap_state(self):
        """Check initial connectivity and authenticate."""
        try:
            try:
                connectivity = await self.page.connectivity.get_connectivity()
                state.is_online = ft.ConnectivityType.NONE not in connectivity
            except Exception as exc:
                logger.warning("Connectivity check failed: %s", exc)
                state.is_online = True

            if not state.is_online:
                return

            try:
                auth_info = await self.colab_service.check_auth()
                state.is_authenticated = auth_info.get("authenticated", False)
                state.auth_email = auth_info.get("email", "")
                if state.is_authenticated:
                    state.onboarding_done = True
                    await self.storage.set(constants.STORAGE_ONBOARDING_DONE, "true")
                else:
                    onboarding_done = await self.storage.get(
                        constants.STORAGE_ONBOARDING_DONE
                    )
                    state.onboarding_done = onboarding_done == "true"
            except Exception as ex:
                logger.warning("Auth check failed: %s", ex)
                state.is_authenticated = False
                state.onboarding_done = False

            # Preload active sessions ONLY if authenticated
            if state.is_authenticated:
                try:
                    state.active_sessions = (
                        await self.colab_service.list_sessions(
                            auth_method=state.auth_method
                        )
                        or []
                    )
                except Exception as ex:
                    logger.warning("Preload sessions failed: %s", ex)
                    state.active_sessions = []
            else:
                state.active_sessions = []
        finally:
            state.app_ready = True
            try:
                self.page.update()
            except Exception:
                logger.exception("Suppressed exception")

    def _register_lifecycle_handlers(self):
        page = self.page

        # Disconnect cleanup
        def _cleanup_sessions():
            if state.keep_alive_on_disconnect or not state.active_sessions:
                return
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                for s in state.active_sessions:
                    name = s.get("name")
                    if name:
                        try:
                            loop.run_until_complete(
                                self.colab_service.stop_session(
                                    name, auth_method=state.auth_method
                                )
                            )
                        except Exception as exc:
                            logger.warning(
                                "Cleanup failed for session %s: %s", name, exc
                            )
                loop.close()
            except Exception as e:
                logger.warning("atexit cleanup encountered error: %s", e)

        atexit.register(_cleanup_sessions)

        async def on_disconnect(e=None):
            if state.keep_alive_on_disconnect or not state.active_sessions:
                return
            for s in state.active_sessions:
                name = s.get("name")
                if name:
                    try:
                        await self.colab_service.stop_session(
                            name, auth_method=state.auth_method
                        )
                    except Exception as exc:
                        logger.warning(
                            "Disconnect cleanup failed for %s: %s", name, exc
                        )

        page.on_disconnect = on_disconnect

        # Android lifecycle handler
        async def _on_lifecycle_change(e: ft.AppLifecycleStateChangeEvent):
            if e.state not in (
                ft.AppLifecycleState.RESUME,
                ft.AppLifecycleState.SHOW,
            ):
                return

            logger.info("[lifecycle] app resumed — re-probing connectivity")
            try:
                connectivity = await page.connectivity.get_connectivity()
                state.is_online = ft.ConnectivityType.NONE not in connectivity
            except Exception as exc:
                logger.warning("[lifecycle] connectivity probe failed: %s", exc)

            if state.is_online and state.active_sessions:
                dead = [
                    name
                    for name, task in self.colab_service._keep_alive_tasks.items()
                    if task.done()
                ]
                for session_name in dead:
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
                            "[lifecycle] restarting keep-alive for %s",
                            session_name,
                        )
                        self.colab_service._start_in_process_keep_alive(
                            session_name, ep, state.auth_method
                        )

            # Terminal WebSockets die while the app is backgrounded (Colab's
            # proxy closes idle sockets) but the PTYs stay alive — re-attach.
            reconnect_terminals = getattr(state, "terminal_reconnect", None)
            if state.is_online and callable(reconnect_terminals):
                try:
                    await reconnect_terminals()
                    logger.info("[lifecycle] terminal reconnect pass complete")
                except Exception:
                    logger.exception("[lifecycle] terminal reconnect failed")

        page.on_app_lifecycle_state_change = _on_lifecycle_change

        # Android hardware BACK: close the active subview (session/history)
        # before letting the system pop the root view.
        async def _on_view_pop(e):
            if state.active_subview:
                self._navigate("/home")
            elif len(page.views) > 1:
                page.views.pop()
                page.route = page.views[-1].route

        page.on_view_pop = _on_view_pop

    def _on_error(self, e):
        logger.error("Global Page Error: %s", getattr(e, "data", e))
        try:
            show_notification(
                self.page,
                "Something went wrong. Please try again.",
                is_error=True,
                persist=True,
            )
        except Exception:
            logger.exception("Suppressed exception")


async def main(page: ft.Page):
    controller = AppController(page)
    await controller.init()


if __name__ == "__main__":
    import os

    assets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    ft.run(main, assets_dir=assets_path)
