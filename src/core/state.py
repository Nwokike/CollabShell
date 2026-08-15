from typing import ClassVar

"""Observable application state."""

import flet as ft


@ft.observable
class AppState:
    # ── Session state ─────────────────────────────────────────────────────────
    active_sessions: ClassVar[list] = []
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

    # ── Settings (every CLI flag exposed) ─────────────────────────────────────
    auth_method: str = "oauth2"
    default_gpu: str = ""
    default_tpu: str = ""
    default_timeout: int = 30
    keep_alive_enabled: bool = True
    keep_alive_on_disconnect: bool = True
    default_log_format: str = "ipynb"
    drive_mount_path: str = "/content/drive"
    logtostderr: bool = False

    # ── Auth ──────────────────────────────────────────────────────────────────
    is_authenticated: bool = False
    auth_email: str = ""
    auth_error: str = ""

    # ── UI ────────────────────────────────────────────────────────────────────
    theme_mode: ft.ThemeMode = ft.ThemeMode.SYSTEM
    is_loading: bool = False
    app_ready: bool = False
    cli_available: bool = False
    update_available_version: str | None = None
    onboarding_done: bool = False

    # ── History ───────────────────────────────────────────────────────────────
    log_session_names: ClassVar[list] = []
    log_events: ClassVar[list] = []

    # ── Connectivity ─────────────────────────────────────────────────────────
    is_online: bool = True

    # ── Services ──────────────────────────────────────────────────────────────
    ad_service = None

    def __init__(self):
        self.active_sessions = []
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
