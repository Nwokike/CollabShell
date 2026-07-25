import flet as ft

from components.notebook_toolbar import build_notebook_toolbar
from core import constants, tokens
from core.styles import build_banner_ad, glass_card, hardware_badge, status_dot
from core.theme import AppColors
from services.storage_service import StorageService
from views.session.controller import SessionController
from views.session.ipynb import on_export_ipynb, on_import_ipynb
from views.session.layout import build_action_row, build_keep_alive_card
from views.session.vm_ops import (
    check_session,
    on_auth_gcp,
    on_keep_alive,
    on_keep_alive_disconnect,
    on_mount_drive,
    on_restart,
    on_stop,
    on_view_logs,
)


def build_session_view(
    page: ft.Page,
    colab_service,
    state,
    session_name: str,
    initial_tab: str = "notebook",
    on_back=None,
    navigate=None,
    snack=None,
    theme_btn=None,
    storage: StorageService = None,
) -> ft.View:
    if storage is None:
        storage = StorageService(page)

    if not hasattr(state, "notebook_cells"):
        state.notebook_cells = []

    session = next(
        (s for s in state.active_sessions if s.get("name") == session_name), None
    )

    if not session:
        content_err = ft.Column(
            controls=[
                ft.AppBar(
                    leading=ft.IconButton(
                        ft.Icons.ARROW_BACK_ROUNDED, on_click=on_back
                    ),
                    title=ft.Text("Session Not Found"),
                ),
                ft.Container(
                    content=ft.Text(
                        constants.ERR_NO_SESSION, color=ft.Colors.ON_SURFACE_VARIANT
                    ),
                    padding=tokens.SPACE_XL,
                    alignment=ft.Alignment.CENTER,
                ),
            ],
            expand=True,
        )
        return ft.View(f"/session?session={session_name}", [content_err], padding=0)

    accel = session.get("accelerator", "NONE")
    variant = session.get("variant", "DEFAULT")
    is_running = session.get("running") is not None

    status_header = glass_card(
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        status_dot(is_running),
                        ft.Text(
                            session_name,
                            size=tokens.FONT_XL,
                            weight=ft.FontWeight.W_700,
                            expand=True,
                        ),
                        hardware_badge(accel, variant),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=tokens.SPACE_MD,
                ),
                ft.Text(
                    session.get("status", "IDLE"),
                    size=tokens.FONT_SM,
                    color=AppColors.SUCCESS
                    if is_running
                    else ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM
        ),
    )

    from views.terminal_view import build_terminal_panel

    def _on_terminal_fullscreen_change(is_fullscreen: bool):
        if status_header:
            status_header.visible = not is_fullscreen
        if app_tabs:
            app_tabs.visible = not is_fullscreen
        if page:
            page.update()

    terminal_panel, terminal_init_func = build_terminal_panel(
        page,
        session_name,
        colab_service,
        snack,
        on_fullscreen_change=_on_terminal_fullscreen_change,
    )
    _terminal_initialized = {"value": False}
    tabs_ref = ft.Ref[ft.Tabs]()
    notebook_container_ref = ft.Ref[ft.Container]()
    terminal_container_ref = ft.Ref[ft.Container]()

    def _on_tab_change(e):
        idx = int(e.data) if e and e.data else 0
        if notebook_container_ref.current and terminal_container_ref.current:
            notebook_container_ref.current.visible = idx == 0
            terminal_container_ref.current.visible = idx == 1
        if idx == 1 and not _terminal_initialized["value"]:
            _terminal_initialized["value"] = True
            page.run_task(terminal_init_func)
        page.update()

    def _switch_to_terminal_tab():
        if tabs_ref.current:
            tabs_ref.current.selected_index = 1
        if not _terminal_initialized["value"]:
            _terminal_initialized["value"] = True
            page.run_task(terminal_init_func)

    cells_list = ft.Column(spacing=0)

    ctrl = SessionController(
        page=page,
        colab_service=colab_service,
        state=state,
        session_name=session_name,
        storage=storage,
        snack=snack,
        navigate=navigate,
        on_back=on_back,
        cells_list=cells_list,
    )
    ctrl.tabs_ref = tabs_ref
    ctrl.notebook_container_ref = notebook_container_ref
    ctrl.terminal_container_ref = terminal_container_ref

    async def _on_files(e):
        if not await check_session(ctrl):
            return
        if navigate:
            await navigate(f"/files?session={session_name}")

    async def _on_open_browser(e):
        if not await check_session(ctrl):
            return
        try:
            url = await colab_service.get_session_url(
                session_name, auth_method=state.auth_method
            )
            await ft.UrlLauncher().launch_url(url)
        except Exception as ex:
            if snack:
                snack(f"Error: {ex}")

    action_row = build_action_row(
        page=page,
        on_files=lambda e: page.run_task(_on_files, e),
        on_mount_drive=lambda e: page.run_task(on_mount_drive, ctrl, e),
        on_auth_gcp=lambda e: page.run_task(on_auth_gcp, ctrl, e),
        on_open_browser=lambda e: page.run_task(_on_open_browser, e),
        on_terminal=lambda e: _switch_to_terminal_tab(),
        on_view_logs=lambda e: page.run_task(on_view_logs, ctrl, e),
        on_restart=lambda e: page.run_task(on_restart, ctrl, e),
        on_stop=lambda e: page.run_task(on_stop, ctrl, e),
    )

    page.run_task(ctrl.load_notebook)

    notebook_section = ft.Container(
        content=cells_list,
        padding=ft.Padding(tokens.SPACE_MD, 0, tokens.SPACE_MD, tokens.SPACE_XL),
    )

    toolbar = build_notebook_toolbar(
        on_add_code=lambda e: ctrl.add_cell("code"),
        on_add_markdown=lambda e: ctrl.add_cell("markdown"),
        on_clear_all=ctrl.clear_all_outputs,
        on_export_ipynb=lambda e: page.run_task(on_export_ipynb, ctrl, e),
        on_import_ipynb=lambda e: page.run_task(on_import_ipynb, ctrl, e),
        on_open_terminal=_switch_to_terminal_tab,
    )

    keep_alive_card = build_keep_alive_card(
        page=page,
        state=state,
        on_keep_alive=lambda e: on_keep_alive(ctrl, e),
        on_keep_alive_disconnect=lambda e: on_keep_alive_disconnect(ctrl, e),
    )

    notebook_body = ft.Column(
        controls=[
            keep_alive_card,
            action_row,
            notebook_section,
            build_banner_ad(page),
            ft.Container(height=tokens.SPACE_XXXL * 3),
        ],
        spacing=tokens.SPACE_SM,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    notebook_container = ft.Container(
        ref=notebook_container_ref,
        content=ft.Stack(
            controls=[
                notebook_body,
                ft.Container(
                    content=toolbar,
                    bottom=0,
                    left=0,
                    right=0,
                ),
            ],
            expand=True,
        ),
        expand=True,
        visible=initial_tab == "notebook",
    )

    terminal_container = ft.Container(
        ref=terminal_container_ref,
        content=terminal_panel,
        expand=True,
        visible=initial_tab == "terminal",
    )

    if initial_tab == "terminal":
        _terminal_initialized["value"] = True
        page.run_task(terminal_init_func)

    stacked_content = ft.Stack(
        controls=[
            notebook_container,
            terminal_container,
        ],
        expand=True,
    )

    app_tabs = ft.Tabs(
        ref=tabs_ref,
        length=2,
        selected_index=0 if initial_tab == "notebook" else 1,
        on_change=_on_tab_change,
        expand=False,
        content=ft.Column(
            controls=[
                ft.TabBar(
                    height=48,
                    label_padding=ft.Padding(16, 0, 16, 0),
                    divider_color=ft.Colors.TRANSPARENT,
                    tabs=[
                        ft.Tab(
                            label=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.EDIT_NOTE_ROUNDED, size=tokens.ICON_MD
                                    ),
                                    ft.Text(
                                        "Notebook",
                                        size=tokens.FONT_MD,
                                        weight=ft.FontWeight.W_500,
                                    ),
                                ],
                                spacing=tokens.SPACE_SM,
                                alignment=ft.MainAxisAlignment.CENTER,
                            )
                        ),
                        ft.Tab(
                            label=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.TERMINAL_ROUNDED, size=tokens.ICON_MD
                                    ),
                                    ft.Text(
                                        "Terminal",
                                        size=tokens.FONT_MD,
                                        weight=ft.FontWeight.W_500,
                                    ),
                                ],
                                spacing=tokens.SPACE_SM,
                                alignment=ft.MainAxisAlignment.CENTER,
                            )
                        ),
                    ],
                ),
            ],
            spacing=0,
        ),
    )

    main_layout = ft.Column(
        controls=[
            status_header,
            app_tabs,
            stacked_content,
        ],
        spacing=0,
        expand=True,
    )

    return ft.View(
        route=f"/session?session={session_name}",
        controls=[main_layout],
        padding=0,
        appbar=ft.AppBar(
            leading=ft.Container(
                content=ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    on_click=on_back,
                    icon_size=tokens.ICON_MD,
                    tooltip="Back to Home",
                ),
                padding=ft.Padding(tokens.SPACE_XS, 0, 0, 0),
            ),
            leading_width=48,
            title=ft.Text(
                "Active Session",
                size=tokens.FONT_LG,
                weight=ft.FontWeight.W_700,
                color=ft.Colors.ON_SURFACE,
            ),
            center_title=True,
            bgcolor=ft.Colors.TRANSPARENT,
            actions=[theme_btn] if theme_btn else None,
        ),
    )
