import logging
import urllib.parse

import flet as ft

from components.offline_flow import OfflineFlow
from core import constants, tokens

logger = logging.getLogger("router")


async def route_change_impl(
    page: ft.Page,
    colab_service,
    state,
    storage,
    navigate,
    show_new_session_sheet,
    snack,
):
    page.views.clear()
    route = page.route
    parsed = urllib.parse.urlparse(route)
    route = parsed.path
    query_params = dict(urllib.parse.parse_qsl(parsed.query))

    async def _global_toggle_theme(e=None):
        if page.theme_mode == ft.ThemeMode.SYSTEM:
            page.theme_mode = ft.ThemeMode.LIGHT
        elif page.theme_mode == ft.ThemeMode.LIGHT:
            page.theme_mode = ft.ThemeMode.DARK
        else:
            page.theme_mode = ft.ThemeMode.SYSTEM

        state.theme_mode = page.theme_mode
        await storage.set(
            constants.STORAGE_THEME,
            page.theme_mode.value,
        )

        if page.theme_mode == ft.ThemeMode.SYSTEM:
            theme_btn.icon = ft.Icons.BRIGHTNESS_AUTO_ROUNDED
        elif page.theme_mode == ft.ThemeMode.LIGHT:
            theme_btn.icon = ft.Icons.LIGHT_MODE_ROUNDED
        else:
            theme_btn.icon = ft.Icons.DARK_MODE_ROUNDED

        page.update()

    current_theme = getattr(state, "theme_mode", ft.ThemeMode.SYSTEM)
    if isinstance(current_theme, str):
        current_theme = ft.ThemeMode(current_theme)
    theme_btn_icon = ft.Icons.BRIGHTNESS_AUTO_ROUNDED
    if current_theme == ft.ThemeMode.LIGHT:
        theme_btn_icon = ft.Icons.LIGHT_MODE_ROUNDED
    elif current_theme == ft.ThemeMode.DARK:
        theme_btn_icon = ft.Icons.DARK_MODE_ROUNDED

    theme_btn = ft.IconButton(
        icon=theme_btn_icon,
        tooltip="Toggle Theme",
        on_click=lambda e: page.run_task(_global_toggle_theme),
    )
    logger.info("Route: %s", route)

    page.views.clear()

    # Onboarding gate
    if not state.onboarding_done and route != "/onboarding":
        page.route = "/onboarding"
        await route_change_impl(
            page, colab_service, state, storage, navigate, show_new_session_sheet, snack
        )
        return

    if route == "/offline":

        async def _on_retry(e):
            connectivity = await state.connectivity.get_connectivity()
            state.is_online = ft.ConnectivityType.NONE not in connectivity
            if state.is_online:
                # Lazy import avoids the router <-> main circular dependency.
                from main import run_initial_route

                page.run_task(run_initial_route)
            else:
                if snack:
                    snack("Still offline. Check your connection.")

        page.views.append(
            ft.View(
                route="/offline",
                controls=[OfflineFlow(on_retry=_on_retry)],
                padding=0,
            )
        )
        page.update()
        return

    if route == "/onboarding":
        from views.onboarding import build_onboarding_view

        view = build_onboarding_view(
            page=page,
            colab_service=colab_service,
            state=state,
            storage=storage,
            on_complete=lambda: page.run_task(navigate, "/home"),
            snack=snack,
        )
        page.views.append(view)

    elif route == "/home" or route == "/":
        from views.home import build_home_view

        view = build_home_view(
            page=page,
            colab_service=colab_service,
            state=state,
            on_new_session=lambda mode: show_new_session_sheet(mode=mode),
            on_session_tap=lambda name: page.run_task(
                navigate, f"/session?session={name}"
            ),
            navigate=navigate,
            on_refresh=lambda e: page.run_task(colab_service.list_sessions, "oauth2"),
            storage=storage,
        )
        page.views.append(view)

    elif route in ["/notebooks_tab", "/terminals_tab", "/files_tab"]:
        from views.session_selector_view import build_session_selector_view

        mode = "notebook"
        if route == "/terminals_tab":
            mode = "terminal"
        elif route == "/files_tab":
            mode = "files"

        view = build_session_selector_view(
            page=page,
            colab_service=colab_service,
            state=state,
            mode=mode,
            on_new_session=lambda m: show_new_session_sheet(mode=m),
            navigate=navigate,
            theme_btn=theme_btn,
        )
        page.views.append(view)

    elif route == "/session":
        from views.session import build_session_view

        session_name = query_params.get("session", "")
        initial_tab = query_params.get("tab", "notebook")
        view = build_session_view(
            page=page,
            colab_service=colab_service,
            state=state,
            session_name=session_name,
            initial_tab=initial_tab,
            on_back=lambda e: page.run_task(navigate, "/home"),
            navigate=navigate,
            snack=snack,
            theme_btn=theme_btn,
            storage=storage,
        )
        page.views.append(view)

    elif route == "/files":
        from views.files import build_files_view

        session_name = query_params.get("session", "")
        view = build_files_view(
            page=page,
            colab_service=colab_service,
            state=state,
            session_name=session_name,
            on_back=lambda e: page.run_task(
                navigate, f"/session?session={urllib.parse.quote(session_name)}"
            ),
            snack=snack,
            theme_btn=theme_btn,
        )
        page.views.append(view)

    elif route == "/terminal":
        from views.terminal_view import build_terminal_view

        session_name = query_params.get("session", "")
        view = build_terminal_view(
            page=page,
            colab_service=colab_service,
            state=state,
            session_name=session_name,
            on_back=lambda e: page.run_task(
                navigate, f"/session?session={session_name}"
            ),
            snack=snack,
            theme_btn=theme_btn,
        )
        page.views.append(view)

    elif route == "/history":
        from views.history_view import build_history_view

        preselected = query_params.get("session", None)
        view = build_history_view(
            page=page,
            colab_service=colab_service,
            state=state,
            preselected_session=preselected,
            navigate=navigate,
            snack=snack,
            theme_btn=theme_btn,
        )
        page.views.append(view)

    elif route == "/settings":
        from views.settings import build_settings_view

        view = build_settings_view(
            page=page,
            colab_service=colab_service,
            state=state,
            storage=storage,
        )
        page.views.append(view)

    else:
        page.route = "/home"
        await route_change_impl(
            page, colab_service, state, storage, navigate, show_new_session_sheet, snack
        )
        return

    # Attach nav bar to tabbed views
    root_routes = {
        "/home",
        "/",
        "/notebooks_tab",
        "/terminals_tab",
        "/files_tab",
        "/settings",
    }
    if page.views and route in root_routes:
        routes = [
            "/home",
            "/notebooks_tab",
            "/terminals_tab",
            "/files_tab",
            "/settings",
        ]
        active_route = route if route != "/" else "/home"
        nav_bar = ft.NavigationBar(
            selected_index=routes.index(active_route) if active_route in routes else 0,
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.HOME_OUTLINED,
                    selected_icon=ft.Icons.HOME_ROUNDED,
                    label=constants.LBL_HOME,
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.NOTE_OUTLINED,
                    selected_icon=ft.Icons.NOTE_ROUNDED,
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

        def on_nav_change(e):
            index = e.control.selected_index
            page.run_task(navigate, routes[index])

        nav_bar.on_change = on_nav_change
        page.views[-1].navigation_bar = nav_bar

    # Attach appbar to tabbed views
    if page.views and route in root_routes:
        top_view = page.views[-1]

        page_tags = {
            "/home": "Home",
            "/": "Home",
            "/notebooks_tab": "Notebooks",
            "/terminals_tab": "Terminals",
            "/files_tab": "Cloud Files",
            "/settings": "Settings",
        }
        tag_text = page_tags.get(route, "Collab Shell")

        page_tag = ft.Container(
            content=ft.Text(
                tag_text,
                size=tokens.FONT_LG,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.ON_SURFACE,
            ),
            padding=ft.Padding(tokens.SPACE_LG, 0, 0, 0),
            alignment=ft.Alignment.CENTER_LEFT,
        )

        if not top_view.appbar:
            top_view.appbar = ft.AppBar()
        top_view.appbar.leading = page_tag
        top_view.appbar.leading_width = 100
        top_view.appbar.title = ft.Container()
        top_view.appbar.center_title = True
        top_view.appbar.actions = [theme_btn]
        top_view.appbar.bgcolor = ft.Colors.TRANSPARENT

    page.update()
