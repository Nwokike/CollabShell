"""AppShell — top-level shell branching onboarding, fullscreen subviews, and dashboard.

Follows the proven SpanInsight & DDGS architecture:
- @ft.component reading observable AppState and ControllerMethods
- Page-level NavigationBar attached to page.views[0].navigation_bar via use_effect
- Clean declarative screen switching with explicit ValueKeys
"""

from __future__ import annotations

import logging

import flet as ft
from flet import Control

from components.offline_flow import OfflineFlow
from core import constants, tokens
from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx

logger = logging.getLogger("AppShell")

_TAB_NAMES = ("Home", "Notebooks", "Terminal", "Files", "Settings")
_TAB_ICONS = (
    ft.Icons.HOME_OUTLINED,
    ft.Icons.EDIT_NOTE_ROUNDED,
    ft.Icons.TERMINAL_OUTLINED,
    ft.Icons.FOLDER_OUTLINED,
    ft.Icons.SETTINGS_OUTLINED,
)
_TAB_SELECTED_ICONS = (
    ft.Icons.HOME_ROUNDED,
    ft.Icons.EDIT_NOTE_ROUNDED,
    ft.Icons.TERMINAL_ROUNDED,
    ft.Icons.FOLDER_ROUNDED,
    ft.Icons.SETTINGS_ROUNDED,
)


@ft.component
def AppShell() -> Control:
    """Top-level shell. Reads observable state; renders Onboarding, Subview, or Dashboard."""
    controller = ft.use_context(ControllerMethodsCtx)
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    page = ft.context.page

    # ── 1. NavigationBar sync via use_effect (Deliberate Page Chrome) ──────────
    def _sync_navigation_bar():
        if not page or not page.views:
            return

        # Hide navigation bar when loading, in onboarding, or inside a subview
        if (
            not state.app_ready
            or not state.onboarding_done
            or not state.is_authenticated
            or bool(state.active_subview)
        ):
            if page.views[0].navigation_bar is not None:
                page.views[0].navigation_bar = None
                try:
                    page.update()
                except Exception:
                    pass
            return

        def _on_tab_change(e):
            idx = e.control.selected_index
            logger.info("Tab changed: %s (index %d)", _TAB_NAMES[idx], idx)
            controller.navigate_tab(idx)

        destinations = [
            ft.NavigationBarDestination(
                icon=icon,
                selected_icon=sel_icon,
                label=label,
            )
            for icon, sel_icon, label in zip(
                _TAB_ICONS, _TAB_SELECTED_ICONS, _TAB_NAMES, strict=True
            )
        ]
        page.views[0].navigation_bar = ft.NavigationBar(
            destinations=destinations,
            selected_index=state.current_tab,
            on_change=_on_tab_change,
            bgcolor=ft.Colors.SURFACE,
            indicator_color=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
            label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        )
        try:
            page.update()
        except Exception:
            pass

    ft.use_effect(
        _sync_navigation_bar,
        [
            state.app_ready,
            state.onboarding_done,
            state.is_authenticated,
            state.active_subview,
            state.current_tab,
        ],
    )

    # ── 2. Loading Splash Screen ──────────────────────────────────────────────
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

    # ── 3. Offline Mode ───────────────────────────────────────────────────────
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

    # ── 4. Onboarding Presentation ────────────────────────────────────────────
    if not state.onboarding_done or not state.is_authenticated:
        from screens.onboarding import OnboardingScreen

        return OnboardingScreen(key=ft.ValueKey("onboarding"))

    # ── 5. Fullscreen Subviews (History / Active Session) ─────────────────────
    if state.active_subview == "history":
        from screens.history import HistoryScreen

        return ft.SafeArea(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.IconButton(
                                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                                    on_click=lambda e: controller.close_history(),
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
                    ft.Container(
                        content=HistoryScreen(key=ft.ValueKey("history_screen")),
                        expand=True,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            expand=True,
        )

    if state.active_subview == "session" and state.active_session_name:
        if state.session_mode == "files":
            from screens.files import FilesScreen

            return ft.SafeArea(
                content=ft.Column(
                    controls=[
                        ft.Container(
                            content=ft.Row(
                                controls=[
                                    ft.IconButton(
                                        icon=ft.Icons.ARROW_BACK_ROUNDED,
                                        on_click=lambda e: controller.close_session(),
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
                            content=FilesScreen(
                                session_name=state.active_session_name,
                                key=ft.ValueKey(f"files_{state.active_session_name}"),
                            ),
                            expand=True,
                        ),
                    ],
                    spacing=0,
                    expand=True,
                ),
                expand=True,
            )

        from screens.session import SessionScreen

        return ft.SafeArea(
            content=SessionScreen(
                session_name=state.active_session_name,
                mode=state.session_mode,
                on_back=controller.close_session,
                key=ft.ValueKey(
                    f"session_{state.active_session_name}_{state.session_mode}"
                ),
            ),
            expand=True,
        )

    # ── 6. Main Tabbed Dashboard Views ────────────────────────────────────────
    theme_icon = (
        ft.Icons.BRIGHTNESS_AUTO_ROUNDED
        if state.theme_mode == ft.ThemeMode.SYSTEM
        else ft.Icons.LIGHT_MODE_ROUNDED
        if state.theme_mode == ft.ThemeMode.LIGHT
        else ft.Icons.DARK_MODE_ROUNDED
    )
    theme_tooltip = (
        "System Theme"
        if state.theme_mode == ft.ThemeMode.SYSTEM
        else "Light Theme"
        if state.theme_mode == ft.ThemeMode.LIGHT
        else "Dark Theme"
    )
    theme_btn = ft.IconButton(
        icon=theme_icon,
        icon_size=tokens.ICON_SM,
        tooltip=theme_tooltip,
        on_click=lambda e: controller.toggle_theme(),
    )

    header_bar = ft.Container(
        content=ft.Row(
            controls=[
                ft.Text(
                    _TAB_NAMES[state.current_tab],
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
                    visible=state.current_tab == 0,
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

    if state.current_tab == 1:
        from screens.session_selector import SessionSelectorTab

        screen = SessionSelectorTab(
            mode="notebook", key=ft.ValueKey("notebook_tab")
        )
    elif state.current_tab == 2:
        from screens.session_selector import SessionSelectorTab

        screen = SessionSelectorTab(
            mode="terminal", key=ft.ValueKey("terminal_tab")
        )
    elif state.current_tab == 3:
        from screens.session_selector import SessionSelectorTab

        screen = SessionSelectorTab(
            mode="files", key=ft.ValueKey("files_tab")
        )
    elif state.current_tab == 4:
        from screens.settings import SettingsScreen

        screen = SettingsScreen(key=ft.ValueKey("settings_tab"))
    else:
        from screens.home import HomeScreen

        screen = HomeScreen(key=ft.ValueKey("home_tab"))

    return ft.SafeArea(
        content=ft.Column(
            controls=[
                header_bar,
                ft.Container(content=screen, expand=True),
            ],
            spacing=0,
            expand=True,
        ),
        expand=True,
    )
