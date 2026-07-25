import logging
import urllib.parse

import flet as ft

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
        is_dark = page.theme_mode == ft.ThemeMode.DARK or (
            page.theme_mode == ft.ThemeMode.SYSTEM
            and page.platform_brightness == ft.Brightness.DARK
        )
        page.theme_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        state.theme_mode = page.theme_mode
        await storage.set(
            constants.STORAGE_THEME,
            "light" if page.theme_mode == ft.ThemeMode.LIGHT else "dark",
        )
        theme_btn.icon = (
            ft.Icons.LIGHT_MODE_ROUNDED
            if page.theme_mode == ft.ThemeMode.DARK
            else ft.Icons.DARK_MODE_ROUNDED
        )
        page.update()

    theme_btn = ft.IconButton(
        icon=ft.Icons.LIGHT_MODE_ROUNDED
        if page.theme_mode == ft.ThemeMode.DARK
        else ft.Icons.DARK_MODE_ROUNDED,
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
    if page.views and route in ("/home", "/", "/history", "/settings"):
        routes = ["/home", "/history", "/settings"]
        nav_bar = ft.NavigationBar(
            selected_index=routes.index(route) if route in routes else 0,
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.HOME_OUTLINED,
                    selected_icon=ft.Icons.HOME_ROUNDED,
                    label=constants.LBL_HOME,
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.HISTORY_OUTLINED,
                    selected_icon=ft.Icons.HISTORY_ROUNDED,
                    label=constants.LBL_HISTORY,
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
    if page.views and route in ("/home", "/", "/history", "/settings"):
        top_view = page.views[-1]
        root_routes = {"/home", "/", "/history", "/settings"}
        if route in root_routes:
            page_tags = {
                "/home": "Home",
                "/": "Home",
                "/history": "History",
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
