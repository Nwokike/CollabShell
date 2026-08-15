"""AppShell — Top-level shell managing navigation, tabs, and full-screen views."""

from __future__ import annotations

import flet as ft

from components.offline_flow import OfflineFlow
from core import constants, tokens
from screens.files import FilesScreen
from screens.history import HistoryScreen
from screens.home import HomeScreen
from screens.onboarding import OnboardingScreen
from screens.session import SessionScreen
from screens.session_selector import SessionSelectorTab
from screens.settings import SettingsScreen
from state import AppStateCtx, ControllerMethodsCtx


@ft.component
def AppShell() -> ft.Control:
    """Root application shell with bottom navigation bar and reactive subviews."""
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    selected_tab, set_selected_tab = ft.use_state(0)
    active_session, set_active_session = ft.use_state(None)
    active_session_mode, set_session_mode = ft.use_state("notebook")
    show_history, set_show_history = ft.use_state(False)

    # Wire controller methods into our local state
    def _open_session(name: str, mode: str):
        set_session_mode(mode)
        set_active_session(name)
        set_show_history(False)

    def _close_session():
        set_active_session(None)

    controller.open_session = _open_session
    controller.close_session = _close_session

    # ── 0. Initial App Loading Screen ─────────────────────────────────────────
    if not state.app_ready:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(
                        ft.Icons.TERMINAL_ROUNDED, size=72, color=ft.Colors.PRIMARY
                    ),
                    ft.Container(height=tokens.SPACE_LG),
                    ft.ProgressRing(
                        width=tokens.SPINNER_MD,
                        height=tokens.SPINNER_MD,
                        stroke_width=3,
                    ),
                    ft.Container(height=tokens.SPACE_SM),
                    ft.Text(
                        "Initializing Colab Shell...",
                        size=tokens.FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

    # ── 1. Offline mode ───────────────────────────────────────────────────────
    if not state.is_online:

        async def _on_retry():
            try:
                connectivity = await page.connectivity.get_connectivity()
                state.is_online = ft.ConnectivityType.NONE not in connectivity
                if state.is_online:
                    controller.show_snack("Back online!")
                else:
                    controller.show_snack("Still offline. Check your connection.")
            except Exception:
                pass

        return OfflineFlow(on_retry=lambda: page.run_task(_on_retry))

    # ── 2. Onboarding flow ────────────────────────────────────────────────────
    if not state.onboarding_done or not state.is_authenticated:
        return OnboardingScreen()

    # ── 3. Active session fullscreen ──────────────────────────────────────────
    if active_session is not None:
        if active_session_mode == "files":
            return ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.IconButton(
                                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                                    on_click=lambda e: set_active_session(None),
                                    icon_size=tokens.ICON_MD,
                                    tooltip="Back to Home",
                                ),
                                ft.Text(
                                    f"Files — {active_session}",
                                    size=tokens.FONT_LG,
                                    weight=ft.FontWeight.W_700,
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_SM,
                        ),
                        padding=ft.Padding(
                            tokens.SPACE_SM,
                            tokens.SPACE_SM,
                            tokens.SPACE_LG,
                            tokens.SPACE_SM,
                        ),
                        bgcolor=ft.Colors.SURFACE,
                    ),
                    ft.Container(
                        content=FilesScreen(session_name=active_session),
                        expand=True,
                    ),
                ],
                spacing=0,
                expand=True,
            )
        return SessionScreen(
            session_name=active_session,
            mode=active_session_mode,
            on_back=lambda: set_active_session(None),
        )

    # ── 4. History Screen fullscreen ──────────────────────────────────────────
    if show_history:
        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK_ROUNDED,
                                on_click=lambda e: set_show_history(False),
                                icon_size=tokens.ICON_MD,
                                tooltip="Back",
                            ),
                            ft.Text(
                                "Execution History",
                                size=tokens.FONT_LG,
                                weight=ft.FontWeight.W_700,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=tokens.SPACE_SM,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_SM,
                        tokens.SPACE_SM,
                        tokens.SPACE_LG,
                        tokens.SPACE_SM,
                    ),
                    bgcolor=ft.Colors.SURFACE,
                ),
                ft.Container(content=HistoryScreen(), expand=True),
            ],
            spacing=0,
            expand=True,
        )

    # ── 5. Main Tabbed Navigation ─────────────────────────────────────────────
    tab_screens = [
        HomeScreen(),
        SessionSelectorTab(mode="notebook"),
        SessionSelectorTab(mode="terminal"),
        SessionSelectorTab(mode="files"),
        SettingsScreen(),
    ]

    tab_titles = [
        "Home",
        "Notebooks",
        "Terminals",
        "Cloud Files",
        "Settings",
    ]

    nav_bar = ft.NavigationBar(
        selected_index=selected_tab,
        on_change=lambda e: set_selected_tab(int(e.control.selected_index)),
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.HOME_OUTLINED,
                selected_icon=ft.Icons.HOME_ROUNDED,
                label=constants.LBL_HOME,
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.EDIT_NOTE_ROUNDED,
                selected_icon=ft.Icons.EDIT_NOTE_ROUNDED,
                label="Notebooks",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.TERMINAL_OUTLINED,
                selected_icon=ft.Icons.TERMINAL_ROUNDED,
                label="Terminal",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.FOLDER_OUTLINED,
                selected_icon=ft.Icons.FOLDER_ROUNDED,
                label="Files",
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

    theme_btn = ft.IconButton(
        icon=ft.Icons.DARK_MODE_ROUNDED
        if state.theme_mode == ft.ThemeMode.LIGHT
        else ft.Icons.LIGHT_MODE_ROUNDED,
        icon_size=tokens.ICON_SM,
        tooltip="Toggle Theme",
        on_click=lambda e: controller.toggle_theme(),
    )

    header_bar = ft.Container(
        content=ft.Row(
            controls=[
                ft.Text(
                    tab_titles[selected_tab],
                    size=tokens.FONT_LG,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.ON_SURFACE,
                ),
                ft.Container(expand=True),
                ft.IconButton(
                    icon=ft.Icons.HISTORY_ROUNDED,
                    icon_size=tokens.ICON_SM,
                    tooltip="Execution History",
                    on_click=lambda e: set_show_history(True),
                    visible=selected_tab == 0,
                ),
                theme_btn,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM
        ),
        bgcolor=ft.Colors.SURFACE,
    )

    return ft.Column(
        controls=[
            header_bar,
            ft.Container(
                content=tab_screens[selected_tab],
                expand=True,
            ),
            nav_bar,
        ],
        spacing=0,
        expand=True,
    )
