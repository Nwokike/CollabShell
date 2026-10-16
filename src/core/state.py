"""Observable application state — single source of truth."""

from __future__ import annotations

from typing import ClassVar

import flet as ft


@ft.observable
class AppState:
    # ── Session state ─────────────────────────────────────────────────────────
    active_sessions: ClassVar[list] = []
    active_session_name: str = ""
    session_mode: str = "notebook"  # "notebook", "terminal", "files"
    selected_session_name: str = ""
    is_provisioning: bool = False
    is_executing: bool = False
    is_uploading: bool = False
    is_downloading: bool = False
    is_installing: bool = False
    is_mounting: bool = False

    # ── Execution ─────────────────────────────────────────────────────────────
    exec_output_lines: ClassVar[list] = []
    current_exec_file: str = ""
    notebook_cells: ClassVar[list] = []

    # ── File browser ──────────────────────────────────────────────────────────
    current_path: str = "/content"
    file_listing: ClassVar[list] = []
    is_browsing: bool = False

    # ── Navigation & UI ───────────────────────────────────────────────────────
    current_tab: int = 0  # 0=Home, 1=Notebooks, 2=Terminal, 3=Files, 4=Settings
    active_subview: str = ""  # "", "session", "history"
    theme_mode: ft.ThemeMode = ft.ThemeMode.SYSTEM
    theme_revision: int = 0  # bumped on platform-brightness change (SYSTEM mode)
    terminal_settings_rev: int = 0  # bumped when terminal settings change (FAB rebuild)
    # Bumped whenever a metered assistant turn settles, so the credit pill
    # re-reads the balance without a full rebuild.
    credits_revision: int = 0
    # Callable set by the active TerminalPanel; invoked on app RESUME so
    # dropped terminal WebSockets re-attach to their still-alive PTYs.
    terminal_reconnect = None
    is_loading: bool = False
    app_ready: bool = False
    cli_available: bool = False
    update_available: bool = False
    update_data: dict | None = None
    onboarding_done: bool = False

    # ── Settings (every CLI flag exposed) ─────────────────────────────────────
    auth_method: str = "oauth2"
    default_gpu: str = ""
    default_tpu: str = ""
    default_high_mem: bool = False
    default_timeout: int = 30
    # Never mutated in place: hydration/settings always REPLACE the dict, and
    # readers copy values out. Single app-wide instance (see bottom of file).
    default_env: dict = {}  # noqa: RUF012
    keep_alive_on_disconnect: bool = True
    default_log_format: str = "ipynb"
    drive_mount_path: str = "/content/drive"
    logtostderr: bool = True

    # ── Auth ──────────────────────────────────────────────────────────────────
    is_authenticated: bool = False
    auth_email: str = ""
    auth_error: str = ""
    # Assistant premium (higher daily credit cap). The license Worker is
    # authoritative; see services/premium_service.py.
    is_premium: bool = False

    # ── Assistant (AI) ──────────────────────────────────────────────────────
    ai_mode: bool = False  # off until the user turns it on in Settings
    ai_model: str = "auto"
    # An ADVANCED OVERRIDE, not the normal path. Empty means the app probes
    # 8082..8092 and embeds its own router (services/router.py), which is what
    # makes the assistant work out of the box.
    ai_router_url: str = ""
    ai_help: bool = True  # inject the bundled SKILL.md into the system prompt
    # How hard the model thinks before answering: one of `THINKING_DEPTHS`.
    # "auto" is stored by name but sends nothing, leaving the router's own
    # default in force — the same rule both reference apps use.
    ai_thinking: str = "auto"
    # Router lifecycle, owned by services/router.py and carried to the UI by
    # services/router_watchdog.py. Written only on a real change, so the status
    # loop never repaints for nothing.
    # One of: ready | stopped | unavailable | starting
    ai_router_status: str = "starting"
    ai_router_port: int | None = None
    # OS notifications for finished work. On by default once the user grants
    # permission (granting IS the opt-in), with a Settings switch to turn the
    # channel off without revoking the OS permission.
    notify_enabled: bool = True
    # The open conversation (single owner: conversation_service).
    active_assistant_conversation: str = ""
    # Cached list for the history dialog (refreshed by conversation_service).
    assistant_conversations: ClassVar[list] = []
    # Chat lifecycle. The session object is retained on the page across
    # minimize/restore, so these exist for the shell and tests to read —
    # the transcript itself is never torn down by minimizing.
    assistant_open: bool = False
    assistant_minimized: bool = False

    # ── History ───────────────────────────────────────────────────────────────
    log_session_names: ClassVar[list] = []
    log_events: ClassVar[list] = []

    # ── Connectivity ─────────────────────────────────────────────────────────
    is_online: bool = True

    # ── Services ──────────────────────────────────────────────────────────────
    ad_service = None

    def __init__(self):
        self.active_sessions = []
        self.active_session_name = ""
        self.session_mode = "notebook"
        self.current_tab = 0
        self.active_subview = ""
        self.exec_output_lines = []
        self.file_listing = []
        self.log_session_names = []
        self.log_events = []
        self.update_available = False
        self.update_data = None
        self.onboarding_done = False
        self.app_ready = False
        self.is_online = True
        self.ad_service = None
        self.notebook_cells = []


state = AppState()
