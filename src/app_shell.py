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

    # ── 0. Initial App Loading Screen (Matching SpanInsights) ─────────────────
    if not state.app_ready:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Image(
                        src="icon.png",
                        width=tokens.HERO_ICON_SIZE,
                        height=tokens.HERO_ICON_SIZE,
                        fit=ft.BoxFit.CONTAIN,
                    ),
                    ft.Container(height=tokens.SPACE_XL),
                    ft.ProgressRing(
                        width=tokens.SPINNER_LG,
                        height=tokens.SPINNER_LG,
                        stroke_width=3,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            expand=True,
            alignment=ft.Alignment.CENTER,
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
                    controller.show_snack(constants.ERR_NETWORK)
            except Exception:
                pass

        return OfflineFlow(on_retry=lambda: page.run_task(_on_retry))

    # ── 2. Onboarding flow ────────────────────────────────────────────────────
    if not state.onboarding_done:
        return OnboardingScreen()

    # ── 3. Active session fullscreen ──────────────────────────────────────────
    if state.active_fullscreen == "session":
        return SessionScreen(
            session_name=state.active_session_name,
            mode=state.active_session_mode,
            on_back=controller.close_fullscreen,
        )

    if state.active_fullscreen == "files":
        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK_ROUNDED,
                                on_click=lambda e: controller.close_fullscreen(),
                                icon_size=tokens.ICON_MD,
                                tooltip="Back to Home",
                            ),
                            ft.Text(
                                f"{constants.LBL_FILES} — {state.active_session_name}",
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
                    content=FilesScreen(session_name=state.active_session_name),
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        )

    # ── 4. History Screen fullscreen ──────────────────────────────────────────
    if state.active_fullscreen == "history":
        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK_ROUNDED,
                                on_click=lambda e: controller.close_fullscreen(),
                                icon_size=tokens.ICON_MD,
                                tooltip="Back",
                            ),
                            ft.Text(
                                constants.LBL_HISTORY,
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
    tab_titles = [
        constants.LBL_HOME,
        constants.LBL_NOTEBOOKS,
        constants.LBL_TERMINAL,
        constants.LBL_CLOUD_FILES,
        constants.LBL_SETTINGS,
    ]

    if state.selected_tab == 1:
        screen = SessionSelectorTab(mode="notebook", key=ft.ValueKey("notebooks"))
    elif state.selected_tab == 2:
        screen = SessionSelectorTab(mode="terminal", key=ft.ValueKey("terminal"))
    elif state.selected_tab == 3:
        screen = SessionSelectorTab(mode="files", key=ft.ValueKey("files"))
    elif state.selected_tab == 4:
        screen = SettingsScreen(key=ft.ValueKey("settings"))
    else:
        screen = HomeScreen(key=ft.ValueKey("home"))

    nav_bar = ft.NavigationBar(
        selected_index=state.selected_tab,
        on_change=lambda e: controller.navigate_tab(int(e.control.selected_index)),
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.HOME_OUTLINED,
                selected_icon=ft.Icons.HOME_ROUNDED,
                label=constants.LBL_HOME,
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.EDIT_NOTE_ROUNDED,
                selected_icon=ft.Icons.EDIT_NOTE_ROUNDED,
                label=constants.LBL_NOTEBOOKS,
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.TERMINAL_OUTLINED,
                selected_icon=ft.Icons.TERMINAL_ROUNDED,
                label=constants.LBL_TERMINAL,
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.FOLDER_OUTLINED,
                selected_icon=ft.Icons.FOLDER_ROUNDED,
                label=constants.LBL_FILES,
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
                    tab_titles[state.selected_tab],
                    size=tokens.FONT_LG,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.ON_SURFACE,
                ),
                ft.Container(expand=True),
                ft.IconButton(
                    icon=ft.Icons.HISTORY_ROUNDED,
                    icon_size=tokens.ICON_SM,
                    tooltip=constants.LBL_HISTORY,
                    on_click=lambda e: controller.open_history(),
                    visible=state.selected_tab == 0,
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
                content=screen,
                expand=True,
            ),
            nav_bar,
        ],
        spacing=0,
        expand=True,
    )
