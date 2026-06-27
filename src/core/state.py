"""Observable application state."""

import flet as ft


@ft.observable
class AppState:
    # ── Session state ─────────────────────────────────────────────────────────
    active_sessions: list = []
    selected_session_name: str = ""
    is_provisioning: bool = False
    is_executing: bool = False
    is_uploading: bool = False
    is_downloading: bool = False
    is_installing: bool = False
    is_mounting: bool = False

    # ── Execution ─────────────────────────────────────────────────────────────
    exec_output_lines: list = []
    current_exec_file: str = ""

    # ── File browser ──────────────────────────────────────────────────────────
    current_path: str = "content"
    file_listing: list = []
    is_browsing: bool = False

    # ── Settings (every CLI flag exposed) ─────────────────────────────────────
    auth_method: str = "oauth2"
    default_gpu: str = ""
    default_tpu: str = ""
    default_timeout: int = 30
    keep_alive_enabled: bool = True
    auto_stop_on_close: bool = False
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
    cli_version: str = ""
    cli_available: bool = False
    update_available_version: str | None = None
    onboarding_done: bool = False

    # ── History ───────────────────────────────────────────────────────────────
    history_sessions: list = []
    session_history: list = []

    # ── Services ──────────────────────────────────────────────────────────────
    ad_service = None

    def __init__(self):
        self.active_sessions = []
        self.exec_output_lines = []
        self.file_listing = []
        self.history_sessions = []
        self.session_history = []
        self.update_available_version = None
        self.onboarding_done = False
        self.ad_service = None


state = AppState()
