import asyncio

import flet as ft

from components.session_card import build_session_card
from core import tokens


def build_sessions_section(
    page: ft.Page, colab_service, state, on_session_tap, storage
):
    sessions_list = ft.Container(
        content=ft.Column(spacing=tokens.SPACE_SM),
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
    )

    async def update_sessions_ui():
        sessions_list.content.controls.clear()
        if state.is_loading:
            sessions_list.content.controls.append(
                ft.Container(
                    content=ft.ProgressRing(width=30, height=30),
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding(0, tokens.SPACE_XXL, 0, tokens.SPACE_XXL),
                )
            )
        elif not state.active_sessions:
            sessions_list.content.controls.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(
                                ft.Icons.CLOUD_OFF_ROUNDED,
                                size=tokens.ICON_XXL,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            ft.Text(
                                "No active sessions",
                                size=tokens.FONT_MD,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                "Tap 'New Session' to create a cloud runtime",
                                size=tokens.FONT_XS,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=tokens.SPACE_SM,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_XL,
                        tokens.SPACE_XXL,
                        tokens.SPACE_XL,
                        tokens.SPACE_XXL,
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            )
        for s in state.active_sessions:
            sessions_list.content.controls.append(
                build_session_card(
                    session=s,
                    on_click=lambda e, sn=s["name"]: (
                        on_session_tap(sn) if on_session_tap else None
                    ),
                )
            )
        await asyncio.sleep(0)
        page.update()

    async def load_sessions():
        await asyncio.sleep(0.1)  # Let the view mount on mobile
        try:
            state.is_loading = True
            await update_sessions_ui()
            sessions = await colab_service.list_sessions(auth_method=state.auth_method)
            state.active_sessions = sessions
            state.is_loading = False

            # Clean up notebook cache for deleted sessions
            if storage:
                active_names = [s["name"] for s in state.active_sessions]
                page.run_task(storage.cleanup_orphaned_notebooks, active_names)

            await update_sessions_ui()
        except Exception:
            state.is_loading = False
            await update_sessions_ui()

    sessions_section_header = ft.Container(
        content=ft.Row(
            controls=[
                ft.Text(
                    "ACTIVE SESSIONS",
                    size=tokens.FONT_SM,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.PRIMARY,
                    style=ft.TextStyle(letter_spacing=1),
                ),
                ft.IconButton(
                    icon=ft.Icons.REFRESH_ROUNDED,
                    icon_size=tokens.ICON_SM,
                    tooltip="Refresh active sessions",
                    on_click=lambda e: page.run_task(load_sessions),
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_XS,
        ),
    )

    try:
        if getattr(page, "_session", getattr(page, "session", None)):
            page.run_task(load_sessions)
    except RuntimeError:
        pass

    return sessions_section_header, sessions_list, load_sessions
