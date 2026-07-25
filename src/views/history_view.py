"""History view — session logs with filters and export."""

from __future__ import annotations

import os

import flet as ft

from components.brand_header import build_brand_header
from core import constants, tokens
from core.styles import build_native_ad, glass_card, section_header
from core.theme import AppColors


def build_history_view(
    page: ft.Page,
    colab_service,
    state,
    preselected_session: str | None = None,
    navigate=None,
    snack=None,
    theme_btn=None,
) -> ft.View:
    """Build the history view with session selector, event list, and export."""

    selected_session = preselected_session or ""
    events = []
    event_filter = "all"
    lines_limit = 50
    is_loading = False

    session_dropdown_ref = ft.Ref[ft.Dropdown]()
    filter_ref = ft.Ref[ft.Dropdown]()
    lines_ref = ft.Ref[ft.Dropdown]()

    async def _load_sessions():
        nonlocal is_loading
        is_loading = True
        page.update()
        try:
            sessions = await colab_service.list_log_sessions()
            state.log_session_names = sessions
            if session_dropdown_ref.current:
                session_dropdown_ref.current.options = [
                    ft.dropdown.Option(key=s, text=s) for s in sessions
                ]
                if selected_session and selected_session in sessions:
                    session_dropdown_ref.current.value = selected_session
                elif sessions:
                    session_dropdown_ref.current.value = sessions[0]
        except Exception as ex:
            if snack:
                snack(f"Error loading sessions: {ex}")
        is_loading = False
        page.update()

        # Auto-load events for the selected session
        if session_dropdown_ref.current and session_dropdown_ref.current.value:
            await _load_events()

    async def _load_events():
        nonlocal events, is_loading
        sess = (
            session_dropdown_ref.current.value if session_dropdown_ref.current else ""
        )
        if not sess:
            return
        is_loading = True
        page.update()
        try:
            et = None if event_filter == "all" else event_filter
            events = await colab_service.get_log(sess, lines=lines_limit, event_type=et)
            state.log_events = events
        except Exception as ex:
            if snack:
                snack(f"Error: {ex}")
            events = []
        is_loading = False
        page.update()

    def _on_session_change(e):
        nonlocal selected_session
        selected_session = e.control.value
        page.run_task(_load_events)

    def _on_filter_change(e):
        nonlocal event_filter
        event_filter = e.control.value
        page.run_task(_load_events)

    def _on_lines_change(e):
        nonlocal lines_limit
        val = e.control.value
        lines_limit = int(val) if val != "all" else None
        page.run_task(_load_events)

    async def _on_export(e):
        sess = (
            session_dropdown_ref.current.value if session_dropdown_ref.current else ""
        )
        if not sess:
            if snack:
                snack("Select a session first")
            return

        if state.ad_service:
            await state.ad_service.show_interstitial()

        fmt = state.default_log_format or "ipynb"
        if page.platform in [
            ft.PagePlatform.ANDROID,
            ft.PagePlatform.ANDROID_TV,
            ft.PagePlatform.IOS,
        ]:
            export_dir = "/storage/emulated/0/Download"
        else:
            export_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(export_dir, exist_ok=True)
        output_path = os.path.join(export_dir, f"{sess}_log.{fmt}")

        if snack:
            snack(f"Exporting to {fmt}...")
        try:
            await colab_service.export_log(sess, output_path)
            if snack:
                snack(f"✅ Exported to {output_path}")
        except Exception as ex:
            if snack:
                snack(f"❌ {ex}")

    # ── Event type badge ──────────────────────────────────────────────────────
    def _event_badge(event_type):
        colors = {
            "execution": AppColors.BADGE_GPU,
            "file_operation": AppColors.BADGE_TPU,
            "automation": AppColors.SUCCESS,
            "session_created": AppColors.BADGE_CPU,
            "session_terminated": AppColors.ERROR,
            "stdin_request": AppColors.WARNING,
            "input_reply": AppColors.WARNING,
        }
        icons = {
            "execution": ft.Icons.CODE_ROUNDED,
            "file_operation": ft.Icons.FOLDER_ROUNDED,
            "automation": ft.Icons.SETTINGS_ROUNDED,
            "session_created": ft.Icons.ADD_CIRCLE_ROUNDED,
            "session_terminated": ft.Icons.STOP_CIRCLE_ROUNDED,
            "stdin_request": ft.Icons.INPUT_ROUNDED,
            "input_reply": ft.Icons.OUTPUT_ROUNDED,
        }
        color = colors.get(event_type, AppColors.BADGE_CPU)
        icon = icons.get(event_type, ft.Icons.INFO_ROUNDED)

        return ft.Container(
            content=ft.Icon(icon, size=tokens.ICON_SM, color=ft.Colors.WHITE),
            width=tokens.STEP_BADGE_SIZE,
            height=tokens.STEP_BADGE_SIZE,
            border_radius=tokens.STEP_BADGE_RADIUS,
            bgcolor=color,
            alignment=ft.Alignment.CENTER,
        )

    def _build_event_item(event):
        etype = event.get("event_type", "unknown")
        ts = event.get("timestamp", "").split(".")[0].replace("T", " ")

        subtitle = ""
        if etype == "execution":
            code = event.get("code", "")
            subtitle = code[:80].replace("\n", " ") + ("..." if len(code) > 80 else "")
        elif etype == "file_operation":
            subtitle = (
                f"{event.get('op', '')} → {event.get('path', event.get('remote', ''))}"
            )
        elif etype == "automation":
            subtitle = event.get("op", "")
        elif etype == "session_created":
            subtitle = f"Hardware: {event.get('accelerator', 'CPU')}"
        elif etype == "session_terminated":
            subtitle = event.get("reason", "")

        return ft.Container(
            content=ft.Row(
                controls=[
                    _event_badge(etype),
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(
                                        etype.replace("_", " ").title(),
                                        size=tokens.FONT_MD,
                                        weight=ft.FontWeight.W_500,
                                    ),
                                    ft.Text(
                                        ts,
                                        size=tokens.FONT_XXS,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ft.Text(
                                subtitle,
                                size=tokens.FONT_XS,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            )
                            if subtitle
                            else ft.Container(height=0),
                        ],
                        spacing=tokens.SPACE_XXS,
                        expand=True,
                    ),
                ],
                spacing=tokens.SPACE_MD,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding(
                tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD
            ),
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
            border_radius=tokens.RADIUS_MD,
            border=ft.Border.all(
                tokens.DIVIDER_THICKNESS,
                ft.Colors.with_opacity(tokens.OPACITY_CONTAINER, ft.Colors.ON_SURFACE),
            ),
            margin=ft.Margin(0, tokens.SPACE_XXS, 0, tokens.SPACE_XXS),
        )

    def _build_event_list():
        if is_loading:
            return ft.Container(
                content=ft.ProgressRing(
                    width=tokens.SPINNER_LG, height=tokens.SPINNER_LG
                ),
                alignment=ft.Alignment.CENTER,
                padding=tokens.SPACE_XXL,
            )

        if not events:
            return ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(
                            ft.Icons.HISTORY_ROUNDED,
                            size=tokens.ICON_XXL,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            "No history events",
                            size=tokens.FONT_MD,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            "Execute code or manage files to create history",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=tokens.SPACE_SM,
                ),
                alignment=ft.Alignment.CENTER,
                padding=tokens.SPACE_XXL,
            )

        return ft.Column(
            controls=[_build_event_item(ev) for ev in reversed(events)],
            spacing=tokens.SPACE_XXS,
        )

    # ── Layout ────────────────────────────────────────────────────────────────
    # Load sessions on creation
    page.run_task(_load_sessions)

    view_content = ft.Column(
        controls=[
            # Brand Header
            build_brand_header(),
            # Filters
            ft.Container(
                content=ft.Column(
                    controls=[
                        section_header("FILTERS"),
                        glass_card(
                            ft.Column(
                                controls=[
                                    ft.Dropdown(
                                        ref=session_dropdown_ref,
                                        label="Session",
                                        options=[],
                                        border_radius=tokens.RADIUS_MD,
                                        on_select=_on_session_change,
                                    ),
                                    ft.Row(
                                        controls=[
                                            ft.Dropdown(
                                                ref=filter_ref,
                                                label="Event Type",
                                                options=[
                                                    ft.dropdown.Option(
                                                        "all", "All Events"
                                                    ),
                                                    ft.dropdown.Option(
                                                        "execution", "Executions"
                                                    ),
                                                    ft.dropdown.Option(
                                                        "file_operation", "File Ops"
                                                    ),
                                                    ft.dropdown.Option(
                                                        "automation", "Automation"
                                                    ),
                                                    ft.dropdown.Option(
                                                        "session_created",
                                                        "Session Created",
                                                    ),
                                                ],
                                                value="all",
                                                border_radius=tokens.RADIUS_MD,
                                                on_select=_on_filter_change,
                                                expand=True,
                                            ),
                                            ft.Dropdown(
                                                ref=lines_ref,
                                                label="Show",
                                                options=[
                                                    ft.dropdown.Option("10", "Last 10"),
                                                    ft.dropdown.Option("50", "Last 50"),
                                                    ft.dropdown.Option(
                                                        "100", "Last 100"
                                                    ),
                                                    ft.dropdown.Option("all", "All"),
                                                ],
                                                value="50",
                                                border_radius=tokens.RADIUS_MD,
                                                on_select=_on_lines_change,
                                                width=120,
                                            ),
                                        ],
                                        spacing=tokens.SPACE_SM,
                                    ),
                                    ft.OutlinedButton(
                                        content=ft.Text(
                                            f"Export as .{state.default_log_format or 'ipynb'}"
                                        ),
                                        icon=ft.Icons.DOWNLOAD_ROUNDED,
                                        on_click=lambda e: page.run_task(_on_export, e),
                                        width=float("inf"),
                                    ),
                                ],
                                spacing=tokens.SPACE_MD,
                            )
                        ),
                    ],
                    spacing=0,
                ),
                padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
            ),
            # Event list
            section_header("EVENTS"),
            ft.Container(
                content=_build_event_list(),
                expand=True,
                padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
            ),
            build_native_ad(page, size="small"),
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    appbar = ft.AppBar(
        leading=ft.IconButton(
            ft.Icons.ARROW_BACK_ROUNDED,
            on_click=lambda e: page.run_task(navigate, "/home") if navigate else None,
        ),
        title=ft.Text(constants.LBL_HISTORY, weight=ft.FontWeight.BOLD),
        center_title=False,
        bgcolor=ft.Colors.SURFACE,
        actions=[theme_btn] if theme_btn else [],
    )

    return ft.View(
        route="/history",
        controls=[view_content],
        padding=0,
        appbar=appbar,
    )
