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
from components.shortcuts_help import build_help_button, open_shortcuts_help
from core import constants, tokens
from core.shortcuts import Binding, shortcuts_router
from core.theme import brand_color
from hooks.use_keyboard_shortcuts import use_keyboard_shortcuts
from state import AppStateCtx, ControllerMethodsCtx

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
    page = ft.context.page

    # ── 0. Global keyboard shortcuts (desktop) ────────────────────────────────
    # Registered first so screen contexts (session, files) shadow these via the
    # router's most-recent-first matching. Kept live by reading observable
    # state inside the provider, which runs at event time.
    def _global_bindings():
        bindings = []
        if state.app_ready and state.onboarding_done and state.is_authenticated:
            if not state.active_subview:
                bindings.extend(
                    (
                        Binding(str(i + 1), ctrl=True),
                        lambda i=i: controller.navigate_tab(i),
                    )
                    for i in range(len(_TAB_NAMES))
                )
            bindings.append(
                (
                    Binding("F1"),
                    lambda: open_shortcuts_help(
                        page,
                        state.session_mode
                        if state.active_subview == "session"
                        else "global",
                    ),
                )
            )
            # Ctrl+K opens the command palette. Registered here rather than as
            # a screen action so it works from every screen including the
            # fullscreen subviews.
            bindings.append((Binding("k", ctrl=True), _open_palette))
        return bindings

    def _palette_commands():
        """Global commands. Session actions are contributed by the session
        screen; these are the ones available everywhere."""
        commands = [
            ("Command palette", ft.Icons.KEYBOARD_COMMAND_KEY_ROUNDED, "Ctrl+K", _open_palette),
            ("Keyboard shortcuts", ft.Icons.KEYBOARD_ROUNDED, "F1",
             lambda: open_shortcuts_help(page, "global")),
        ]
        if state.ai_mode:
            commands.append(
                (
                    "Open Assistant",
                    tokens.ASSISTANT_ICON,
                    "Chat with the assistant",
                    lambda: controller.open_assistant(),
                )
            )
        commands.extend(
            ("Go to " + name, ft.Icons.LAUNCH_ROUNDED, f"Ctrl+{i + 1}",
             lambda i=i: controller.navigate_tab(i))
            for i, name in enumerate(_TAB_NAMES)
        )
        commands.append(
            ("Toggle theme", ft.Icons.BRIGHTNESS_6_ROUNDED, "Light / dark / system",
             controller.toggle_theme)
        )
        return commands

    def _open_palette():
        from components.command_palette import open_command_palette

        open_command_palette(page, _palette_commands())

    def _register_global_shortcuts():
        return shortcuts_router.register(_global_bindings)

    ft.on_mounted(_register_global_shortcuts)
    use_keyboard_shortcuts(shortcuts_router)

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
                    logger.exception("Suppressed exception")
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
            logger.exception("Suppressed exception")

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

    # ── 1b. Assistant FAB (Deliberate Page Chrome) ──────────────────────────
    # The chat is a peer of the shell, not a route, so it rides on its own
    # view on top of views[0] — which means the shell's FAB is simply not
    # rendered while the chat is open, and comes back when it closes. The
    # chat's own back arrow is the way out; this button is the way back.
    #
    # Both this effect and the session screen write the SAME slot
    # (views[0].floating_action_button), so ownership matters:
    #   - a FAB that is not ours is the session's and must be left alone;
    #   - leaving a session clears the slot, and only a re-run of this effect
    #     (hence state.active_subview in the deps) puts ours back.
    # `_assistant_fab_ref` holds the button we actually created, so identity —
    # not a ValueKey comparison — decides whether the slot is already ours.
    _assistant_fab_ref = ft.Ref[ft.FloatingActionButton]()

    def _sync_assistant_fab():
        if not page or not page.views:
            return
        current = page.views[0].floating_action_button
        ours = current is not None and current is _assistant_fab_ref.current
        # The FAB is always present once the app is up, the way DDGS ships it —
        # it is the entry point to the assistant, so hiding it until ai_mode is
        # on makes the feature undiscoverable. The assistant itself still gates
        # on ai_mode and says so when it is off.
        if not (state.app_ready and state.onboarding_done):
            if ours:
                page.views[0].floating_action_button = None
                _assistant_fab_ref.current = None
                try:
                    page.update()
                except Exception:
                    logger.exception("Suppressed exception")
            return
        if ours:
            # Only the meaning changes between "new chat" and "restore", so
            # relabel in place rather than rebuilding the button.
            wanted = "Back to Assistant" if state.assistant_minimized else "Ask Assistant"
            if current.tooltip != wanted:
                current.tooltip = wanted
                try:
                    page.update()
                except Exception:
                    logger.exception("Suppressed exception")
            return
        if current is not None:
            return  # the session screen owns the slot right now
        # DDGS's recipe verbatim: mini, white icon, brand fill, tooltip only.
        # No shape override (the platform's own roundness is right) and no
        # badge or per-credit rebuild.
        fab = ft.FloatingActionButton(
            icon=tokens.ASSISTANT_ICON,
            foreground_color=ft.Colors.WHITE,
            bgcolor=brand_color(page),
            mini=True,
            tooltip="Back to Assistant"
            if state.assistant_minimized
            else "Ask Assistant",
            on_click=lambda e: controller.open_assistant(),
        )
        _assistant_fab_ref.current = fab
        page.views[0].floating_action_button = fab
        try:
            page.update()
        except Exception:
            logger.exception("Suppressed exception")

    ft.use_effect(
        _sync_assistant_fab,
        [
            state.app_ready,
            state.onboarding_done,
            state.is_authenticated,
            # Relabel when the chat is minimized vs closed, and restore the FAB
            # after a session: the session screen owns
            # views[0].floating_action_button while it is open, so leaving it
            # clears the slot and only a re-run of this effect puts the
            # assistant button there again.
            state.assistant_minimized,
            state.active_subview,
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
                logger.exception("Suppressed exception")

        return OfflineFlow(on_retry=lambda: page.run_task(_on_retry))

    # ── 4. Onboarding Presentation ────────────────────────────────────────────
    if not state.onboarding_done or not state.is_authenticated:
        from screens.onboarding import OnboardingScreen

        return OnboardingScreen(key=ft.ValueKey("onboarding"))

    # ── 5. Fullscreen Subviews (History / Active Session) ─────────────────────
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
                                ft.Container(expand=True),
                                build_help_button(page, "global"),
                                theme_btn,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_SM,
                        ),
                        padding=ft.Padding(
                            tokens.SPACE_SM,
                            tokens.SPACE_SM,
                            tokens.SPACE_MD,
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
                                    ft.Container(expand=True),
                                    build_help_button(page, "files"),
                                    theme_btn,
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=tokens.SPACE_SM,
                            ),
                            padding=ft.Padding(
                                tokens.SPACE_SM,
                                tokens.SPACE_SM,
                                tokens.SPACE_MD,
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

    def _build_version_chip():
        """Sherlock/KTV-style version chip in top-right header: shows current version
        normally, flips to an Update pill when a newer build is found."""
        if state.update_available:
            update_data = state.update_data or {}
            label = (
                update_data.get("version", "Update")
                if update_data.get("type") != "announcement"
                else "News"
            )
            content = ft.Row(
                controls=[
                    ft.Text(
                        f"Update: {label} Available!"
                        if update_data.get("type") != "announcement"
                        else "News",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.PRIMARY,
                        no_wrap=True,
                    ),
                    ft.Container(
                        width=6,
                        height=6,
                        border_radius=3,
                        bgcolor=ft.Colors.PRIMARY,
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            return ft.Container(
                content=content,
                padding=ft.Padding(10, 4, 10, 4),
                border_radius=10,
                bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.PRIMARY),
                border=ft.Border.all(1.5, ft.Colors.PRIMARY),
                ink=True,
                tooltip="New update available — tap to view",
                on_click=lambda e: controller.open_version_dialog(),
            )
        return ft.Container(
            content=ft.Text(
                f"v{constants.APP_VERSION}",
                size=11,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.ON_SURFACE_VARIANT,
                no_wrap=True,
            ),
            padding=ft.Padding(10, 4, 10, 4),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE_VARIANT),
            ink=True,
            tooltip="What's New — version & changelog",
            on_click=lambda e: controller.open_version_dialog(),
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
                _build_version_chip(),
                build_help_button(page, "global"),
                theme_btn,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_XS,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM
        ),
        bgcolor=ft.Colors.SURFACE,
    )

    if state.current_tab == 1:
        from screens.session_selector import SessionSelectorTab

        screen = SessionSelectorTab(mode="notebook", key=ft.ValueKey("notebook_tab"))
    elif state.current_tab == 2:
        from screens.session_selector import SessionSelectorTab

        screen = SessionSelectorTab(mode="terminal", key=ft.ValueKey("terminal_tab"))
    elif state.current_tab == 3:
        from screens.session_selector import SessionSelectorTab

        screen = SessionSelectorTab(mode="files", key=ft.ValueKey("files_tab"))
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
