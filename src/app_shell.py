"""AppShell — Top-level shell managing navigation, tabs, and full-screen views.

Follows the SpanInsights & DDGS architecture:
- Hooks into observable state
- Attaches NavigationBar & AppBar to page.views[0] via use_effect
- Dynamically renders active screen (Onboarding, Tabs, or Full-screen Views)
"""

from __future__ import annotations

import logging

import flet as ft
from flet import Control

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

logger = logging.getLogger("AppShell")

_TAB_NAMES = (
    constants.LBL_HOME,
    constants.LBL_NOTEBOOKS,
    constants.LBL_TERMINAL,
    constants.LBL_FILES,
    constants.LBL_SETTINGS,
)
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
    """Root application shell with bottom navigation bar and reactive subviews."""
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)

    # ── Sync NavigationBar & AppBar on page.views[0] ─────────────
    def _sync_bars():
        from flet import context

        page = context.page
        if not page or not page.views:
            return

        # Hide bars during initial boot, onboarding, or full-screen views
        if (
            not state.app_ready
            or not state.onboarding_done
            or state.active_fullscreen is not None
        ):
            if page.views[0].navigation_bar is not None:
                page.views[0].navigation_bar = None
            if page.views[0].appbar is not None:
                page.views[0].appbar = None
            try:
                page.update()
            except Exception:
                pass
            return

        def _on_tab_change(e):
            idx = int(e.control.selected_index)
            logger.info("Navigated to tab '%s' (index %d)", _TAB_NAMES[idx], idx)
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
            selected_index=state.selected_tab,
            on_change=_on_tab_change,
            bgcolor=ft.Colors.SURFACE,
            indicator_color=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
            label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        )

        def _get_theme_icon():
            if page.theme_mode == ft.ThemeMode.DARK:
                return ft.Icons.DARK_MODE_ROUNDED
            elif page.theme_mode == ft.ThemeMode.LIGHT:
                return ft.Icons.LIGHT_MODE_ROUNDED
            return ft.Icons.BRIGHTNESS_AUTO_ROUNDED

        theme_btn = ft.IconButton(
            icon=_get_theme_icon(),
            icon_size=tokens.ICON_SM,
            tooltip="Toggle Theme",
            on_click=lambda e: controller.toggle_theme(),
        )

        history_btn = ft.IconButton(
            icon=ft.Icons.HISTORY_ROUNDED,
            icon_size=tokens.ICON_SM,
            tooltip=constants.LBL_HISTORY,
            on_click=lambda e: controller.open_history(),
            visible=state.selected_tab == 0,
        )

        tag_text = (
            _TAB_NAMES[state.selected_tab]
            if 0 <= state.selected_tab < len(_TAB_NAMES)
            else constants.APP_NAME
        )
        page_tag = ft.Container(
            content=ft.Text(
                tag_text,
                size=tokens.FONT_LG,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.ON_SURFACE,
            ),
            padding=ft.Padding(16, 0, 0, 0),
            alignment=ft.Alignment.CENTER_LEFT,
        )

        page.views[0].appbar = ft.AppBar(
            leading=page_tag,
            leading_width=140,
            actions=[history_btn, theme_btn],
            center_title=False,
            bgcolor=ft.Colors.SURFACE,
        )

        try:
            page.update()
        except Exception:
            pass

    ft.use_effect(
        _sync_bars,
        [
            state.app_ready,
            state.selected_tab,
            state.active_fullscreen,
            state.onboarding_done,
            state.theme_mode,
        ],
    )

    # ── Screen switching ─────────────────────────────────────────
    if not state.app_ready:
        screen = ft.Container(
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
    elif not state.is_online:
        from flet import context

        page = context.page

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

        screen = OfflineFlow(on_retry=lambda: page.run_task(_on_retry))
    elif not state.onboarding_done:
        screen = OnboardingScreen()
    elif state.active_fullscreen == "history":
        screen = ft.Column(
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
    elif state.active_fullscreen == "session":
        screen = SessionScreen(
            session_name=state.active_session_name,
            mode=state.active_session_mode,
            on_back=controller.close_fullscreen,
        )
    elif state.active_fullscreen == "files":
        screen = ft.Column(
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
    else:
        if state.selected_tab == 1:
            screen = SessionSelectorTab(mode="notebook", key=ft.ValueKey("notebooks"))
        elif state.selected_tab == 2:
            screen = SessionSelectorTab(mode="terminal", key=ft.ValueKey("terminals"))
        elif state.selected_tab == 3:
            screen = SessionSelectorTab(mode="files", key=ft.ValueKey("files"))
        elif state.selected_tab == 4:
            screen = SettingsScreen(key=ft.ValueKey("settings"))
        else:
            screen = HomeScreen(key=ft.ValueKey("home"))

    return ft.SafeArea(content=screen, expand=True)
