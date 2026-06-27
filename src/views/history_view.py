"""History view — session logs with filters and export."""

from __future__ import annotations

import flet as ft
import os

from core import tokens
from core.styles import section_header, build_banner_ad
from core.theme import AppColors


def build_history_view(
    page: ft.Page,
    colab_service,
    state,
    preselected_session: str = None,
    snack=None,
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
            state.history_sessions = sessions
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
            state.session_history = events
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

        fmt = state.default_log_format or "ipynb"
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
            content=ft.Icon(icon, size=tokens.ICON_SM, color="#FFFFFF"),
            width=28,
            height=28,
            border_radius=14,
            bgcolor=color,
            alignment=ft.Alignment.CENTER,
        )

    def _build_event_item(event):
        etype = event.get("event_type", "unknown")
        ts = event.get("timestamp", "").split(".")[0].replace("T", " ")

        # Build subtitle based on event type
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
        )

    def _build_event_list():
        if is_loading:
            return ft.Container(
                content=ft.ProgressRing(width=30, height=30),
                alignment=ft.Alignment.CENTER,
                padding=tokens.SPACE_XXL,
            )

        if not events:
            return ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(
                            ft.Icons.HISTORY_ROUNDED,
                            size=48,
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
            # Filters
            ft.Container(
                content=ft.Column(
                    controls=[
                        section_header("SESSION"),
                        ft.Container(
                            content=ft.Dropdown(
                                ref=session_dropdown_ref,
                                label="Session",
                                options=[],
                                prefix_icon=ft.Icons.LABEL_OUTLINE_ROUNDED,
                                border_radius=tokens.RADIUS_MD,
                                on_change=_on_session_change,
                            ),
                            padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
                        ),
                        ft.Container(
                            content=ft.Row(
                                controls=[
                                    ft.Dropdown(
                                        ref=filter_ref,
                                        label="Event Type",
                                        options=[
                                            ft.dropdown.Option("all", "All Events"),
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
                                                "session_created", "Session Created"
                                            ),
                                        ],
                                        value="all",
                                        border_radius=tokens.RADIUS_MD,
                                        on_change=_on_filter_change,
                                        expand=True,
                                    ),
                                    ft.Dropdown(
                                        ref=lines_ref,
                                        label="Show",
                                        options=[
                                            ft.dropdown.Option("10", "Last 10"),
                                            ft.dropdown.Option("50", "Last 50"),
                                            ft.dropdown.Option("100", "Last 100"),
                                            ft.dropdown.Option("all", "All"),
                                        ],
                                        value="50",
                                        border_radius=tokens.RADIUS_MD,
                                        on_change=_on_lines_change,
                                        width=120,
                                    ),
                                ],
                                spacing=tokens.SPACE_SM,
                            ),
                            padding=ft.Padding(
                                tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                            ),
                        ),
                        # Export button
                        ft.Container(
                            content=ft.OutlinedButton(
                                content=ft.Text(
                                    f"Export as .{state.default_log_format or 'ipynb'}"
                                ),
                                icon=ft.Icons.DOWNLOAD_ROUNDED,
                                on_click=lambda e: page.run_task(_on_export, e),
                                width=float("inf"),
                            ),
                            padding=ft.Padding(
                                tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, 0
                            ),
                        ),
                    ],
                    spacing=0,
                ),
            ),
            ft.Divider(height=1),
            # Event list
            section_header("EVENTS"),
            ft.Container(
                content=_build_event_list(),
                expand=True,
            ),
            build_banner_ad(page),
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    return ft.View(
        route="/history",
        controls=[view_content],
        padding=0,
    )
