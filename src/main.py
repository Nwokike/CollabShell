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


def _install_bytes_safe_streams():
    """Make stdout/stderr tolerate bytes writes.

    The packaged runtime (serious-python) replaces sys.stdout with a writer
    that only accepts str, but click/typer (used inside colab_cli) decides
    to write bytes when the stream has no usable `encoding` attribute —
    crashing e.g. `sync_sessions` with "TypeError: write() argument must be
    str, not bytes" on every startup. Wrapping the runtime streams with a
    decoding adapter fixes that without touching colab_cli.
    """

    class _BytesSafeStream:
        def __init__(self, inner):
            self._inner = inner

        def write(self, data):
            if isinstance(data, (bytes, bytearray)):
                data = bytes(data).decode("utf-8", errors="ignore")
            return self._inner.write(data)

        def flush(self):
            try:
                return self._inner.flush()
            except Exception:
                pass

        def isatty(self):
            try:
                return self._inner.isatty()
            except Exception:
                return False

        def __getattr__(self, name):
            return getattr(self._inner, name)

    for stream_name in ("stdout", "stderr"):
        inner = getattr(sys, stream_name, None)
        if inner is None or isinstance(inner, _BytesSafeStream):
            continue
        setattr(sys, stream_name, _BytesSafeStream(inner))


_install_bytes_safe_streams()
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
from services.update_service import UpdateService
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

# No Windows event-loop policy is set, deliberately. Both DDGS and lm-router run
# on Windows without one, and nothing here needs `add_reader` — the only API
# that requires the Selector loop. Stdin is a Flet dialog
# (`core/stdin_hook.py`), not an OS reader. The policy this replaced was
# deprecated in 3.14 and is removed in 3.16, so it was a warning now and a crash
# later.


class AppController:
    """Initializes backend services, handles lifecycle events, and mounts the AppShell."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.storage: StorageService | None = None
        self.ad_service: AdService | None = None
        self.colab_service: ColabService | None = None
        self.update_service: UpdateService | None = None

    async def check_for_updates(self, notify_if_latest: bool = False) -> None:
        """Check version.json on main for a newer build or announcement.

        Silent on failure; only a mandatory update auto-opens the dialog.
        """
        if not self.update_service:
            return
        update_info = await self.update_service.check_for_update()
        if update_info:
            state.update_available = True
            state.update_data = update_info
            logger.info(
                "Update available: v%s (build %s, type=%s)",
                update_info.get("version"),
                update_info.get("build_number"),
                update_info.get("type"),
            )
            if update_info.get("mandatory"):
                self.open_version_dialog()
        elif notify_if_latest:
            show_notification(
                page=self.page, message=f"✓ {constants.APP_VERSION} is up to date"
            )

    def open_version_dialog(self) -> None:
        """Open the version dialog (changelog when up to date, update UI
        when a newer build was found)."""
        from components.version_dialog import show_version_dialog

        show_version_dialog(self.page)

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

        # Window-close → auto-stop sessions (when enabled). page.on_disconnect
        # only fires for web session drops and atexit is not guaranteed under
        # Flet 1.0's hard-exit contract — so intercept the native close signal
        # instead: stop sessions first, then destroy the window.
        async def _on_window_event(e):
            from flet.controls.core.window import WindowEventType

            if getattr(e, "type", None) != WindowEventType.CLOSE:
                return
            if not state.keep_alive_on_disconnect and state.active_sessions:
                for s in list(state.active_sessions):
                    name = s.get("name")
                    if name:
                        try:
                            await self.colab_service.stop_session(
                                name,
                                auth_method=state.auth_method,
                                reason="window_close",
                            )
                        except Exception as exc:
                            logger.warning(
                                "Window-close cleanup failed for %s: %s", name, exc
                            )
            try:
                await page.window.destroy()
            except Exception as exc:
                logger.warning("Window destroy failed: %s", exc)

        try:
            page.window.prevent_close = True
            page.window.on_event = _on_window_event
        except Exception as exc:
            logger.debug("Window close interception unavailable: %s", exc)

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
                types = getattr(e, "connectivity", None)
                if types is None:
                    data = getattr(e, "data", None)
                    types = [data] if data is not None else None
            except Exception:
                types = None
            if types is not None and (not types or ft.ConnectivityType.NONE in types):
                state.is_online = False
                state.connectivity_status = "offline"
                if state.auth_status == "unavailable":
                    state.auth_status = "unknown"
            else:
                state.connectivity_status = "checking"
                page.run_task(self._bootstrap_state)
            page.update()

        connectivity.on_change = _on_connectivity_change

        self.storage = StorageService(page)
        self.ad_service = AdService(page)
        state.ad_service = self.ad_service
        await self.ad_service.gather_consent()
        page.run_task(self.ad_service.preload_interstitial)

        self.colab_service = ColabService()
        self.update_service = UpdateService()
        # Assistant services: credit metering and premium entitlement.
        from services.credit_service import CreditService
        from services.license_service import KiriLicenseService
        from services.premium_service import PremiumService

        self.credit_service = CreditService()
        self.license_service = KiriLicenseService(self.storage)
        self.premium_service = PremiumService(page, state, self.storage)
        # Unlock from the cached token, then start the hourly re-check.
        page.run_task(self.premium_service.load_local)
        self.premium_service.start_reconcile_loop()
        # The router status loop. Without it `ai_router_status` is written and
        # nothing reads it: the header pill is built once and would say
        # "Loading models…" forever, however the router's health changed.
        from services.router_watchdog import RouterStatusWatchdog

        self.router_watchdog = RouterStatusWatchdog(page)
        self.router_watchdog.start()

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
                storage=self.storage,
            )

        def _open_assistant():
            from screens.assistant_view import open_assistant

            # The chat is a peer of the shell, not a route, so it is pushed
            # directly onto the view stack and the route is left alone.
            open_assistant(page, state, services)

        def _open_assistant_history(rows):
            from screens.assistant_history import show_history_dialog

            show_history_dialog(page, state, services, list(rows or []))

        def _reveal_cell(session_name: str, cell_id: str):
            from screens.session.notebook_view import reveal_cell

            if reveal_cell(session_name, cell_id):
                return
            show_notification(
                page, "That cell is no longer in the notebook.", is_warning=True
            )

        def _open_terminal(session_name: str):
            """Switch to the terminal tab for a session."""
            # Navigate to the session screen with terminal mode
            state.active_session_name = session_name
            state.session_mode = "terminal"
            _navigate_tab(2)  # Terminal tab

        def _open_notebook(session_name: str):
            """Switch to the notebook tab for a session."""
            state.active_session_name = session_name
            state.session_mode = "notebook"
            _navigate_tab(1)  # Notebooks tab

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
            check_for_updates=self.check_for_updates,
            open_version_dialog=self.open_version_dialog,
            open_assistant=_open_assistant,
            open_assistant_history=_open_assistant_history,
            reveal_cell=_reveal_cell,
            open_terminal=_open_terminal,
            open_notebook=_open_notebook,
        )

        services = Services(
            colab=self.colab_service,
            storage=self.storage,
            ad_service=self.ad_service,
            page=page,
            credits=self.credit_service,
            premium=self.premium_service,
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

        # Update check in the background — pure GET + observable flip, so it
        # can never delay startup. Only a mandatory update auto-opens the
        # dialog; otherwise the version chip / Home banner surface it.
        page.run_task(self.check_for_updates)

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

            saved_high_mem = await self.storage.get(constants.STORAGE_DEFAULT_HIGH_MEM)
            if saved_high_mem is not None:
                state.default_high_mem = saved_high_mem == "true"

            saved_timeout = await self.storage.get(constants.STORAGE_DEFAULT_TIMEOUT)
            if saved_timeout:
                try:
                    state.default_timeout = int(saved_timeout)
                except ValueError:
                    pass

            saved_env = await self.storage.get(constants.STORAGE_DEFAULT_ENV)
            if saved_env:
                try:
                    import json

                    parsed = json.loads(saved_env)
                    if isinstance(parsed, dict):
                        state.default_env = {str(k): str(v) for k, v in parsed.items()}
                except ValueError:
                    pass

            saved_drive_path = await self.storage.get(
                constants.STORAGE_DRIVE_MOUNT_PATH
            )
            if saved_drive_path:
                state.drive_mount_path = saved_drive_path

            # ── Assistant prefs ─────────────────────────────────────────────

            saved_ai_model = await self.storage.get(constants.STORAGE_AI_MODEL)
            if saved_ai_model:
                state.ai_model = saved_ai_model

            # The stored router URL is an ADVANCED OVERRIDE. Empty (the default)
            # means the app probes 8082..8092 and embeds its own router on the
            # first turn, which is the path that works with no setup.
            saved_ai_router = await self.storage.get(constants.STORAGE_AI_ROUTER_URL)
            state.ai_router_url = saved_ai_router or ""

            saved_thinking = await self.storage.get(constants.STORAGE_AI_THINKING)
            if saved_thinking in constants.THINKING_DEPTHS:
                state.ai_thinking = saved_thinking

            # Configure the provider once at startup ONLY when an override
            # exists. Without one there is no port to point at yet — the router
            # is probed lazily on the first turn, because paying an 11-port scan
            # before the UI is responsive is a bad first launch. A bad saved URL
            # must not block boot, so this stays wrapped.
            if state.ai_router_url:
                try:
                    from services.ai_service import configure_provider

                    configure_provider(state.ai_router_url)
                except Exception as ex:
                    logger.warning("AI provider configuration skipped: %s", ex)

            saved_logtostderr = await self.storage.get(constants.STORAGE_LOGTOSTDERR)
            if saved_logtostderr is not None:
                state.logtostderr = saved_logtostderr == "true"
            else:
                state.logtostderr = True
        except Exception as e:
            logger.warning("Failed to restore some preferences: %s", e)

    async def _refresh_auth_state(self) -> bool:
        """Verify Google reachability and auth without treating timeouts as sign-out."""
        try:
            await self.colab_service._ensure_online()
        except Exception as exc:
            state.is_online = False
            state.connectivity_status = "offline"
            if state.auth_status == "unavailable":
                state.auth_status = "unknown"
            state.auth_error = (
                "Could not reach Google services. Check your connection and retry."
            )
            logger.warning("Google reachability check failed (%s)", type(exc).__name__)
            return False

        state.is_online = True
        state.connectivity_status = "online"
        try:
            auth_info = await self.colab_service.check_auth()
        except Exception as exc:
            state.auth_status = "unavailable"
            state.auth_error = (
                "Could not verify sign-in with Google "
                f"({type(exc).__name__}). Check your connection and retry."
            )
            logger.warning("Auth verification failed (%s)", type(exc).__name__)
            return False

        auth_status = auth_info.get("status")
        if auth_status is None:
            auth_status = (
                "authenticated"
                if auth_info.get("authenticated", False)
                else "unauthenticated"
            )
        state.auth_status = auth_status
        state.auth_error = auth_info.get("error", "")
        if auth_status == "unavailable":
            logger.warning("Google sign-in verification is temporarily unavailable")
            return False

        state.is_authenticated = bool(auth_info.get("authenticated", False))
        state.auth_email = auth_info.get("email", "")
        return True

    async def _bootstrap_state(self):
        """Check initial connectivity and authenticate."""
        try:
            if not await self._refresh_auth_state():
                state.active_sessions = []
                return

            onboarding_done = await self.storage.get(constants.STORAGE_ONBOARDING_DONE)
            state.onboarding_done = onboarding_done == "true"
            if state.is_authenticated:
                state.onboarding_done = True
                await self.storage.set(constants.STORAGE_ONBOARDING_DONE, "true")

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
                    from services.colab.session_ops import SessionListError

                    if isinstance(ex, SessionListError):
                        logger.warning(
                            "Preload session assignments could not be verified"
                        )
                    else:
                        logger.warning(
                            "Preload sessions failed (%s)", type(ex).__name__
                        )
                    state.active_sessions = []
                # Fire-and-forget usage prefetch (warms the shared 24h cache
                # for Home chip + sheet dialog; never blocks app_ready).
                try:
                    from services.usage_cache import get_usage_cached

                    async def _prefetch_usage():
                        try:
                            from types import SimpleNamespace

                            await get_usage_cached(
                                SimpleNamespace(
                                    colab=self.colab_service, storage=self.storage
                                ),
                                state.auth_method,
                            )
                        except Exception as ex:
                            logger.debug("Usage prefetch failed: %s", ex)

                    self.page.run_task(_prefetch_usage)
                except Exception as ex:
                    logger.debug("Usage prefetch scheduling failed: %s", ex)
            else:
                state.active_sessions = []
        finally:
            state.app_ready = True
            try:
                self.page.update()
            except Exception as exc:
                logger.debug("Bootstrap page update skipped: %s", exc)

    def _register_lifecycle_handlers(self):
        page = self.page

        # Disconnect cleanup
        def _flush_storage():
            # Flet 1.0 hard-exit contract: atexit handlers and unflushed
            # buffered writes are not guaranteed on exit, and StorageService
            # debounces writes by 1s — so flush here. Sync _save_now (atomic
            # tmp+rename, no fsync change). Storage tiers per .flet/README.md:
            # usage cache + notebooks stay in durable data/ (cache/ is OS-
            # purgeable, temp/ is scratch — moving them would risk data loss).
            try:
                self.storage._save_now()
            except Exception as exc:
                logger.warning("Exit storage flush failed: %s", exc)

        def _cleanup_sessions():
            if state.keep_alive_on_disconnect or not state.active_sessions:
                _flush_storage()
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
                                    name,
                                    auth_method=state.auth_method,
                                    reason="process_exit",
                                )
                            )
                        except Exception as exc:
                            logger.warning(
                                "Cleanup failed for session %s: %s", name, exc
                            )
                loop.close()
            except Exception as e:
                logger.warning("atexit cleanup encountered error: %s", e)
            finally:
                _flush_storage()

        atexit.register(_cleanup_sessions)

        # An embedded model router is a daemon thread serving loopback; without
        # this it can outlive the process on some platforms. Registered next to
        # the session cleanup so the two exit paths stay together.
        from services import router as router_service

        atexit.register(router_service.shutdown)
        # The status loop rides the same exit path as the router it watches.
        atexit.register(self.router_watchdog.stop)

        async def on_disconnect(e=None):
            # The chat's turn runs as a task on this page's loop; without this
            # it outlives the page and paints into released widgets.
            from screens.assistant_view import shutdown_assistant

            shutdown_assistant(page)
            # A transport disconnect can be a temporary web refresh or network
            # drop, not an explicit request to terminate remote compute. The
            # confirmed native-window close and process-exit hooks own auto-stop.

        page.on_disconnect = on_disconnect

        # System back (Android gesture, browser back). The assistant chat rides
        # on its own view above the shell, so a back press while it is open must
        # minimize it — otherwise the shell's root view is popped underneath and
        # the app is left with nothing to show.
        # Android lifecycle handler
        async def _on_lifecycle_change(e: ft.AppLifecycleStateChangeEvent):
            if e.state not in (
                ft.AppLifecycleState.RESUME,
                ft.AppLifecycleState.SHOW,
            ):
                return

            logger.info("[lifecycle] app resumed — re-probing connectivity")
            await self._refresh_auth_state()

            if (
                state.is_online
                and state.is_authenticated
                and state.auth_status == "authenticated"
            ):
                # Re-sync assignments first: it re-mints the short-lived
                # runtime-proxy tokens in the local store, so the terminal
                # re-attach below (and any new tab the user opens) presents
                # a fresh token instead of the expired one.
                try:
                    state.active_sessions = await self.colab_service.list_sessions(
                        auth_method=state.auth_method
                    )
                except Exception as exc:
                    from services.colab.session_ops import SessionListError

                    if isinstance(exc, SessionListError):
                        logger.warning(
                            "[lifecycle] session assignments could not be verified"
                        )
                    else:
                        logger.warning(
                            "[lifecycle] session re-sync failed (%s)",
                            type(exc).__name__,
                        )
                    state.active_sessions = []

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
        #
        # The assistant rides its own view above the shell, so BACK while it is
        # open must minimise it — keeping a running turn and its transcript
        # alive — rather than tear it down or pop the shell underneath. This
        # case is checked first because the chat view is the topmost one.
        async def _on_view_pop(e):
            if len(page.views) > 1 and page.views[-1].route == "/assistant":
                from screens.assistant_view import shutdown_assistant

                session = getattr(page, "_assistant_session", None)
                if session is not None:
                    session.close()  # minimize, not shut down
            else:
                shutdown_assistant(page)
            page.update()
            return
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
