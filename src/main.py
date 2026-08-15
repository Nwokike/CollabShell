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
from core.state import state
from core.theme import AppTheme
from services.ad_service import AdService
from services.colab import ColabService
from services.storage_service import StorageService
from state import ControllerMethods, ControllerMethodsCtx, ServiceCtx, Services

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
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

        page.on_error = self._on_error

        # ── Global Services ───────────────────────────────────────────────────
        file_picker = ft.FilePicker()
        page.services.append(file_picker)
        page.file_picker = file_picker

        connectivity = ft.Connectivity()
        page.services.append(connectivity)
        page.connectivity = connectivity
        state.connectivity = connectivity

        self.storage = StorageService(page)
        self.ad_service = AdService(page)
        state.ad_service = self.ad_service
        await self.ad_service.gather_consent()
        page.run_task(self.ad_service.preload_interstitial)

        self.colab_service = ColabService()
        page.run_task(self.colab_service.init)

        # ── Restore Preferences ───────────────────────────────────────────────
        await self._restore_preferences()

        # ── Controller Methods for UI ─────────────────────────────────────────
        def _navigate_tab(tab_idx: int):
            state.selected_tab = tab_idx
            state.active_fullscreen = None
            page.update()

        def _open_history():
            state.active_fullscreen = "history"
            page.update()

        def _open_session(name: str, mode: str = "notebook"):
            state.active_session_name = name
            state.active_session_mode = mode
            state.active_fullscreen = "files" if mode == "files" else "session"
            page.update()

        def _close_fullscreen():
            state.active_fullscreen = None
            page.update()

        def _show_snack(msg: str):
            page.snack_bar = ft.SnackBar(content=ft.Text(msg))
            page.snack_bar.open = True
            page.update()

        def _show_new_session_sheet(mode: str = "notebook"):
            show_new_session_sheet(
                page=page,
                state=state,
                colab_service=self.colab_service,
                ad_service=self.ad_service,
                navigate=None,
                route_change=None,
                snack_func=_show_snack,
                mode=mode,
                ignore_warning=False,
                on_session_created=lambda name: _open_session(name, mode),
            )

        def _toggle_theme():
            page.theme_mode = (
                ft.ThemeMode.DARK
                if page.theme_mode == ft.ThemeMode.LIGHT
                else ft.ThemeMode.LIGHT
            )
            state.theme_mode = page.theme_mode
            page.run_task(
                self.storage.set,
                constants.STORAGE_THEME,
                "dark" if page.theme_mode == ft.ThemeMode.DARK else "light",
            )
            page.update()

        methods = ControllerMethods(
            navigate_tab=_navigate_tab,
            open_history=_open_history,
            close_fullscreen=_close_fullscreen,
            open_session=_open_session,
            close_session=_close_fullscreen,
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

            saved_auth_method = await self.storage.get(constants.STORAGE_AUTH_METHOD)
            if saved_auth_method:
                state.auth_method = saved_auth_method

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

            saved_log_format = await self.storage.get(constants.STORAGE_LOG_FORMAT)
            if saved_log_format:
                state.default_log_format = saved_log_format

            saved_drive_path = await self.storage.get(
                constants.STORAGE_DRIVE_MOUNT_PATH
            )
            if saved_drive_path:
                state.drive_mount_path = saved_drive_path

            saved_logtostderr = await self.storage.get(constants.STORAGE_LOGTOSTDERR)
            if saved_logtostderr is not None:
                state.logtostderr = saved_logtostderr == "true"
        except Exception as e:
            logger.warning("Failed to restore some preferences: %s", e)

    async def _bootstrap_state(self):
        """Check initial connectivity and authenticate."""
        try:
            connectivity = await self.page.connectivity.get_connectivity()
            state.is_online = ft.ConnectivityType.NONE not in connectivity
        except Exception as exc:
            logger.warning("Connectivity check failed: %s", exc)

        if not state.is_online:
            state.app_ready = True
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

        # Preload active sessions
        try:
            state.active_sessions = (
                await self.colab_service.list_sessions(auth_method=state.auth_method)
                or []
            )
        except Exception:
            pass
        finally:
            state.app_ready = True

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

        page.on_app_lifecycle_state_change = _on_lifecycle_change

    def _on_error(self, e):
        logger.error("Global Page Error: %s", getattr(e, "data", e))


async def main(page: ft.Page):
    controller = AppController(page)
    await controller.init()


if __name__ == "__main__":
    import os

    assets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    ft.run(main, assets_dir=assets_path)
