"""HistoryScreen — session event log viewer with filters and export."""

from __future__ import annotations

import os

import flet as ft

from components.brand_header import build_brand_header
from core import tokens
from core.styles import build_banner_ad, glass_card, section_header
from core.theme import AppColors
from state import AppStateCtx, ServiceCtx


@ft.component
def HistoryScreen() -> ft.Control:
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    page = ft.context.page

    sessions, set_sessions = ft.use_state([])
    events, set_events = ft.use_state([])
    selected_session, set_selected_session = ft.use_state("")
    filter_type, set_filter_type = ft.use_state("all")
    max_lines, set_max_lines = ft.use_state("50")
    is_loading, set_loading = ft.use_state(False)

    async def _load_sessions():
        set_loading(True)
        try:
            log_names = await services.colab.list_log_sessions()
            active_names = [s.get("name", "") for s in (state.active_sessions or []) if s.get("name")]
            all_names = list(dict.fromkeys(log_names + active_names))
            set_sessions(all_names)
            if all_names and not selected_session:
                set_selected_session(all_names[0])
                await _load_events(all_names[0])
        except Exception:
            set_sessions([])
        finally:
            set_loading(False)

    async def _load_events(session_name: str):
        if not session_name:
            set_events([])
            return
        set_loading(True)
        try:
            ev = await services.colab.get_log(session_name)
            set_events(ev or [])
        except Exception:
            set_events([])
        finally:
            set_loading(False)

    ft.use_effect(lambda: page.run_task(_load_sessions), [])

    async def _on_session_change(e):
        name = e.control.value or ""
        set_selected_session(name)
        await _load_events(name)

    async def _on_export(e):
        fmt = state.default_log_format or "ipynb"
        if not events or not selected_session:
            return
        try:
            dl_dir = "/storage/emulated/0/Download"
            if not os.path.exists(dl_dir):
                dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(dl_dir, exist_ok=True)
            fname = f"{selected_session}.{fmt}"
            path = os.path.join(dl_dir, fname)

            success = await services.colab.export_log(selected_session, path)
            if success:
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"✅ Exported to {path}"), bgcolor=AppColors.SUCCESS
                )
            else:
                page.snack_bar = ft.SnackBar(
                    ft.Text("❌ Export failed: No events to export"),
                    bgcolor=ft.Colors.ERROR,
                )
            page.snack_bar.open = True
            page.update()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(
                ft.Text(f"❌ Export failed: {ex}"), bgcolor=ft.Colors.ERROR
            )
            page.snack_bar.open = True
            page.update()

    # ── Filter events ─────────────────────────────────────────────────────────
    filtered = [
        ev
        for ev in events
        if filter_type == "all"
        or ev.get("type") == filter_type
        or ev.get("event_type") == filter_type
    ]
    try:
        limit = None if max_lines == "all" else int(max_lines)
        display_events = filtered if limit is None else filtered[-limit:]
    except (ValueError, TypeError):
        display_events = filtered

    # ── Event item ────────────────────────────────────────────────────
    def _build_event_item(ev: dict) -> ft.Control:
        ev_type = ev.get("event_type") or ev.get("type", "unknown")
        ts = ev.get("timestamp", "")
        detail = ev.get("detail") or ev.get("source") or ev.get("code", "")[:80]
        icon_map = {
            "execution": ft.Icons.CODE_ROUNDED,
            "file_operation": ft.Icons.FOLDER_ROUNDED,
            "automation": ft.Icons.AUTO_FIX_HIGH_ROUNDED,
            "session_created": ft.Icons.STORAGE_ROUNDED,
        }
        icon = icon_map.get(ev_type, ft.Icons.CIRCLE_ROUNDED)
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, size=tokens.ICON_SM, color=ft.Colors.PRIMARY),
                    ft.Column(
                        controls=[
                            ft.Text(
                                ev_type.replace("_", " ").title(),
                                size=tokens.FONT_SM,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                detail or "",
                                size=tokens.FONT_XS,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                max_lines=2,
                            ),
                            ft.Text(
                                ts,
                                size=tokens.FONT_XXS,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
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
                1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)
            ),
            margin=ft.Margin(0, tokens.SPACE_XXS, 0, tokens.SPACE_XXS),
        )

    def _build_event_list() -> ft.Control:
        if is_loading and not events:
            return ft.Container(
                content=ft.ProgressRing(
                    width=tokens.SPINNER_LG, height=tokens.SPINNER_LG
                ),
                alignment=ft.Alignment.CENTER,
                padding=tokens.SPACE_XXL,
            )
        if not display_events:
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
            controls=[_build_event_item(ev) for ev in reversed(display_events)],
            spacing=tokens.SPACE_XXS,
        )

    return ft.Column(
        controls=[
            build_brand_header(),
            ft.Container(
                content=ft.Column(
                    controls=[
                        section_header("FILTERS"),
                        glass_card(
                            ft.Column(
                                controls=[
                                    ft.Dropdown(
                                        label="Session",
                                        value=selected_session or None,
                                        options=[
                                            ft.dropdown.Option(n, n) for n in sessions
                                        ],
                                        border_radius=tokens.RADIUS_MD,
                                        on_select=lambda e: page.run_task(
                                            _on_session_change, e
                                        ),
                                    ),
                                    ft.Row(
                                        controls=[
                                            ft.Dropdown(
                                                label="Event Type",
                                                value=filter_type,
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
                                                border_radius=tokens.RADIUS_MD,
                                                on_select=lambda e: set_filter_type(
                                                    e.control.value or "all"
                                                ),
                                                expand=True,
                                            ),
                                            ft.Dropdown(
                                                label="Show",
                                                value=max_lines,
                                                options=[
                                                    ft.dropdown.Option("10", "Last 10"),
                                                    ft.dropdown.Option("50", "Last 50"),
                                                    ft.dropdown.Option(
                                                        "100", "Last 100"
                                                    ),
                                                    ft.dropdown.Option("all", "All"),
                                                ],
                                                border_radius=tokens.RADIUS_MD,
                                                on_select=lambda e: set_max_lines(
                                                    e.control.value or "50"
                                                ),
                                                width=tokens.INPUT_WIDTH_LG,
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
                            ),
                        ),
                    ],
                    spacing=0,
                ),
                padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
            ),
            section_header("EVENTS"),
            ft.Container(
                content=_build_event_list(),
                expand=True,
                padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
            ),
            build_banner_ad(page),
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


__all__ = ["HistoryScreen"]
