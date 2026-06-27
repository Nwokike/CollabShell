"""Session detail view — full control over an active session."""

from __future__ import annotations

import flet as ft

from core import tokens, constants
from core.styles import (
    glass_card,
    section_header,
    hardware_badge,
    status_dot,
    build_banner_ad,
    tip_text,
)
from core.theme import AppColors
from components.terminal import build_terminal
from components.output_panel import build_output_panel


def build_session_view(
    page: ft.Page,
    colab_service,
    state,
    session_name: str,
    on_back=None,
    navigate=None,
    snack=None,
) -> ft.View:
    """Build the session detail view with actions, terminal, and output."""

    code_field_ref = ft.Ref[ft.TextField]()
    output_lines = []

    # Find session data
    session = None
    for s in state.active_sessions:
        if s.get("name") == session_name:
            session = s
            break

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
        return ft.View(
            f"/session?session={session_name}",
            [content_err],
            padding=0,
        )

    accel = session.get("accelerator", "NONE")
    variant = session.get("variant", "DEFAULT")
    is_running = session.get("running") is not None

    # ── Status header ─────────────────────────────────────────────────────────
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
                ft.Text(
                    f"Endpoint: {session.get('endpoint', '')[:20]}...",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM
        ),
    )

    # ── Action grid ───────────────────────────────────────────────────────────
    def _action_card(icon, label, on_click, color=None):
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        icon, size=tokens.ICON_LG, color=color or ft.Colors.PRIMARY
                    ),
                    ft.Text(
                        label,
                        size=tokens.FONT_XS,
                        text_align=ft.TextAlign.CENTER,
                        weight=ft.FontWeight.W_500,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=tokens.SPACE_SM,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            on_click=on_click,
            padding=ft.Padding(
                tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD
            ),
            border_radius=tokens.RADIUS_MD,
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
            ink=True,
            expand=True,
            height=80,
            alignment=ft.Alignment.CENTER,
        )

    async def _on_files(e):
        if navigate:
            await navigate(f"/files?session={session_name}")

    async def _on_open_browser(e):
        try:
            url = await colab_service.get_session_url(
                session_name, auth_method=state.auth_method
            )
            await ft.UrlLauncher().launch_url(url)
        except Exception as ex:
            if snack:
                snack(f"Error: {ex}")

    async def _on_restart(e):
        def _close_and_restart(ev):
            page.pop_dialog()
            page.run_task(_do_restart)

        confirm_dialog = ft.AlertDialog(
            title=ft.Text("Restart Kernel?"),
            content=ft.Text(
                "This will restart the Python kernel. All variables will be lost."
            ),
            actions=[
                ft.TextButton(
                    content=ft.Text("Cancel"), on_click=lambda e: page.pop_dialog()
                ),
                ft.FilledButton(
                    content=ft.Text("Restart"), on_click=_close_and_restart
                ),
            ],
        )
        page.show_dialog(confirm_dialog)

    async def _do_restart():
        if snack:
            snack("Restarting kernel...")
        try:
            await colab_service.restart_kernel(
                session_name, auth_method=state.auth_method
            )
            if snack:
                snack("✅ Kernel restarted")
        except Exception as ex:
            if snack:
                snack(f"❌ {ex}")

    async def _on_stop(e):
        def _close_and_stop(ev):
            page.pop_dialog()
            page.run_task(_do_stop)

        confirm_dialog = ft.AlertDialog(
            title=ft.Text("Stop Session?"),
            content=ft.Text(
                "This will terminate the session and release all resources."
            ),
            actions=[
                ft.TextButton(
                    content=ft.Text("Cancel"), on_click=lambda e: page.pop_dialog()
                ),
                ft.FilledButton(content=ft.Text("Stop"), on_click=_close_and_stop),
            ],
        )
        page.show_dialog(confirm_dialog)

    async def _do_stop():
        if snack:
            snack("Stopping session...")
        try:
            await colab_service.stop_session(
                session_name, auth_method=state.auth_method
            )
            if snack:
                snack("✅ Session terminated")
            # Refresh sessions and go back
            sessions = await colab_service.list_sessions(auth_method=state.auth_method)
            state.active_sessions = sessions
            if on_back:
                on_back(None)
        except Exception as ex:
            if snack:
                snack(f"❌ {ex}")

    async def _on_install(e):
        pkg_field = ft.Ref[ft.TextField]()

        async def _do_install(ev):
            pkgs = pkg_field.current.value.strip() if pkg_field.current else ""
            if not pkgs:
                return
            page.pop_dialog()
            packages = [p.strip() for p in pkgs.split() if p.strip()]
            output_lines.clear()
            state.is_installing = True
            page.update()
            try:
                await colab_service.install_packages(
                    packages,
                    session_name,
                    auth_method=state.auth_method,
                    on_output=lambda t: _append_output(t),
                )
                if snack:
                    snack("✅ Packages installed")
            except Exception as ex:
                if snack:
                    snack(f"❌ {ex}")
            state.is_installing = False
            page.update()

        install_dialog = ft.AlertDialog(
            title=ft.Text("Install Packages"),
            content=ft.Column(
                controls=[
                    ft.TextField(
                        ref=pkg_field,
                        label="Package names",
                        hint_text="numpy pandas matplotlib",
                        prefix_icon=ft.Icons.DOWNLOAD_ROUNDED,
                        border_radius=tokens.RADIUS_MD,
                    ),
                    tip_text(
                        "Separate multiple packages with spaces. Uses uv if available, else pip."
                    ),
                ],
                tight=True,
                spacing=tokens.SPACE_SM,
            ),
            actions=[
                ft.TextButton(
                    content=ft.Text("Cancel"), on_click=lambda e: page.pop_dialog()
                ),
                ft.FilledButton(
                    "Install", on_click=lambda e: page.run_task(_do_install, e)
                ),
            ],
        )
        page.show_dialog(install_dialog)

    async def _on_mount_drive(e):
        output_lines.clear()
        state.is_mounting = True
        if snack:
            snack("Mounting Google Drive...")
        try:
            await colab_service.mount_drive(
                session_name,
                path=state.drive_mount_path,
                auth_method=state.auth_method,
                on_output=lambda t: _append_output(t),
            )
            if snack:
                snack("✅ Drive mounted")
        except Exception as ex:
            if snack:
                snack(f"❌ {ex}")
        state.is_mounting = False
        page.update()

    async def _on_auth_gcp(e):
        output_lines.clear()
        if snack:
            snack("Authenticating with GCP on VM...")
        try:
            await colab_service.auth_gcp_on_vm(
                session_name,
                auth_method=state.auth_method,
                on_output=lambda t: _append_output(t),
            )
            if snack:
                snack("✅ GCP auth complete")
        except Exception as ex:
            if snack:
                snack(f"❌ {ex}")
        page.update()

    async def _on_view_logs(e):
        if navigate:
            await navigate(f"/history?session={session_name}")

    action_grid = ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        _action_card(
                            ft.Icons.FOLDER_ROUNDED,
                            "Files",
                            lambda e: page.run_task(_on_files, e),
                        ),
                        _action_card(
                            ft.Icons.DOWNLOAD_ROUNDED,
                            "Install\nPackages",
                            lambda e: page.run_task(_on_install, e),
                        ),
                        _action_card(
                            ft.Icons.ADD_TO_DRIVE_ROUNDED,
                            "Mount\nDrive",
                            lambda e: page.run_task(_on_mount_drive, e),
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                ft.Row(
                    controls=[
                        _action_card(
                            ft.Icons.SECURITY_ROUNDED,
                            "Auth\nGCP",
                            lambda e: page.run_task(_on_auth_gcp, e),
                        ),
                        _action_card(
                            ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                            "Open in\nBrowser",
                            lambda e: page.run_task(_on_open_browser, e),
                            AppColors.BADGE_TPU,
                        ),
                        _action_card(
                            ft.Icons.HISTORY_ROUNDED,
                            "View\nLogs",
                            lambda e: page.run_task(_on_view_logs, e),
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                ft.Row(
                    controls=[
                        _action_card(
                            ft.Icons.REFRESH_ROUNDED,
                            "Restart\nKernel",
                            lambda e: page.run_task(_on_restart, e),
                            AppColors.WARNING,
                        ),
                        _action_card(
                            ft.Icons.STOP_CIRCLE_ROUNDED,
                            "Stop\nSession",
                            lambda e: page.run_task(_on_stop, e),
                            AppColors.ERROR,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
    )

    # ── Terminal + Output ─────────────────────────────────────────────────────
    def _append_output(text):
        output_lines.append(text)
        page.update()

    async def _on_run_code(e):
        code = code_field_ref.current.value.strip() if code_field_ref.current else ""
        if not code:
            return

        output_lines.clear()
        state.is_executing = True
        page.update()

        try:
            await colab_service.exec_code(
                code,
                session_name,
                timeout=float(state.default_timeout),
                auth_method=state.auth_method,
                on_output=lambda t: _append_output(t),
            )
        except Exception as ex:
            _append_output(f"Error: {ex}")

        state.is_executing = False
        page.update()

    def _on_clear_output(e):
        output_lines.clear()
        page.update()

    terminal_section = ft.Container(
        content=ft.Column(
            controls=[
                section_header("EXECUTE CODE"),
                ft.Container(
                    content=build_terminal(
                        on_run=lambda e: page.run_task(_on_run_code, e),
                        on_clear=_on_clear_output,
                        filename=f"{session_name}.py",
                        is_running=state.is_executing,
                        field_ref=code_field_ref,
                    ),
                    padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
                ),
                ft.Container(
                    content=build_output_panel(
                        lines=output_lines,
                        is_visible=True,
                        on_clear=_on_clear_output,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                    ),
                ),
            ],
            spacing=0,
        ),
    )

    # ── AppBar ────────────────────────────────────────────────────────────────
    app_bar = ft.AppBar(
        leading=ft.IconButton(ft.Icons.ARROW_BACK_ROUNDED, on_click=on_back),
        title=ft.Text(session_name, weight=ft.FontWeight.W_600),
        center_title=True,
    )

    # ── Full view ─────────────────────────────────────────────────────────────
    view_content = ft.Column(
        controls=[
            app_bar,
            ft.Column(
                controls=[
                    status_header,
                    action_grid,
                    terminal_section,
                    ft.Divider(height=tokens.SPACE_SM, color=ft.Colors.TRANSPARENT),
                    build_banner_ad(page),
                    ft.Container(height=tokens.SPACE_XL),
                ],
                spacing=tokens.SPACE_SM,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
        ],
        expand=True,
        spacing=0,
    )

    return ft.View(
        route=f"/session?session={session_name}",
        controls=[view_content],
        padding=0,
    )
