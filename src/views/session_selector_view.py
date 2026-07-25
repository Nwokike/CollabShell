"""Session selector view for the bottom navigation tabs."""

from __future__ import annotations

import flet as ft

from components.session_card import build_session_card
from core import tokens
from core.styles import build_native_ad, section_header


def build_session_selector_view(
    page: ft.Page,
    colab_service,
    state,
    mode: str,
    on_new_session,
    navigate,
    theme_btn=None,
) -> ft.View:
    """Build a view that allows selecting a session or creating a new one."""

    dialog = ft.AlertDialog(modal=True)

    def make_on_select(session_name):
        def handler(e):
            dialog.content = ft.Container(
                width=tokens.DIALOG_WIDTH,
                padding=ft.Padding(
                    tokens.SPACE_XL,
                    tokens.SPACE_XL,
                    tokens.SPACE_XL,
                    tokens.SPACE_XL,
                ),
                content=ft.Column(
                    controls=[
                        ft.ProgressRing(stroke_width=2),
                        ft.Container(height=tokens.HEIGHT_SEPARATOR),
                        ft.Text(
                            f"Opening {session_name}...",
                            size=tokens.FONT_MD,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    tight=True,
                ),
            )
            page.dialog = dialog
            dialog.open = True
            page.update()

            async def _do_navigate():
                import asyncio
                import urllib.parse

                await asyncio.sleep(0.2)
                dialog.open = False
                page.update()
                encoded_session = urllib.parse.quote(session_name)
                if mode == "notebook":
                    page.run_task(navigate, f"/session?session={encoded_session}")
                elif mode == "terminal":
                    page.run_task(
                        navigate, f"/session?session={encoded_session}&tab=terminal"
                    )
                elif mode == "files":
                    page.run_task(navigate, f"/files?session={encoded_session}")

            page.run_task(_do_navigate)

        return handler

    def _on_new(e):
        dialog.content = ft.Container(
            width=tokens.DIALOG_WIDTH,
            padding=ft.Padding(
                tokens.SPACE_XL, tokens.SPACE_XL, tokens.SPACE_XL, tokens.SPACE_XL
            ),
            content=ft.Column(
                controls=[
                    ft.ProgressRing(stroke_width=2),
                    ft.Container(height=tokens.HEIGHT_SEPARATOR),
                    ft.Text(
                        "Preparing...",
                        size=tokens.FONT_MD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
        )
        page.dialog = dialog
        dialog.open = True
        page.update()

        async def _do_new():
            import asyncio

            await asyncio.sleep(0.2)
            dialog.open = False
            page.update()
            if on_new_session:
                on_new_session(mode)

        page.run_task(_do_new)

    # Top action: New Session
    new_session_btn = ft.Container(
        content=ft.ListTile(
            leading=ft.Icon(ft.Icons.ADD_ROUNDED, color=ft.Colors.ON_PRIMARY),
            title=ft.Text(
                "New Session", color=ft.Colors.ON_PRIMARY, weight=ft.FontWeight.BOLD
            ),
        ),
        bgcolor=ft.Colors.PRIMARY,
        border_radius=tokens.RADIUS_LG,
        on_click=_on_new,
        margin=ft.Margin(tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, 0),
    )

    controls = []

    if not state.active_sessions:
        controls.append(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(
                            ft.Icons.STORAGE_ROUNDED,
                            size=tokens.ICON_XXL,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            "No active sessions",
                            size=tokens.FONT_MD,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            "Create a new session to get started.",
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
        )
    else:
        for s in state.active_sessions:
            name = s.get("name", "Unknown")
            controls.append(
                build_session_card(
                    session=s,
                    on_click=make_on_select(name),
                )
            )

    view_title_map = {
        "notebook": "Notebooks",
        "terminal": "Terminals",
        "files": "Cloud Files",
    }
    view_title = view_title_map.get(mode, "Select Session")

    view_content = ft.Column(
        controls=[
            new_session_btn,
            build_native_ad(page, size="small", glass=False),
            section_header("ACTIVE SESSIONS"),
            ft.Column(controls=controls, spacing=0),
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    return ft.View(
        route=f"/{mode}s_tab",
        controls=[view_content],
        padding=0,
        appbar=ft.AppBar(
            title=ft.Text(view_title, weight=ft.FontWeight.BOLD),
            center_title=False,
            bgcolor=ft.Colors.SURFACE,
            actions=[theme_btn] if theme_btn else [],
        ),
    )
