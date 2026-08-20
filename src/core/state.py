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
    is_loading: bool = False
    app_ready: bool = False
    cli_available: bool = False
    update_available_version: str | None = None
    onboarding_done: bool = False

    # ── Settings (every CLI flag exposed) ─────────────────────────────────────
    auth_method: str = "oauth2"
    default_gpu: str = ""
    default_tpu: str = ""
    default_timeout: int = 30
    keep_alive_enabled: bool = True
    keep_alive_on_disconnect: bool = True
    default_log_format: str = "ipynb"
    drive_mount_path: str = "/content/drive"
    logtostderr: bool = True

    # ── Auth ──────────────────────────────────────────────────────────────────
    is_authenticated: bool = False
    auth_email: str = ""
    auth_error: str = ""

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
        self.update_available_version = None
        self.onboarding_done = False
        self.app_ready = False
        self.is_online = True
        self.ad_service = None
        self.notebook_cells = []


state = AppState()
