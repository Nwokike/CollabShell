"""Advanced developer settings section."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.styles import section_card, tip_text


def build_advanced_section(page: ft.Page, state, services) -> ft.Container:
    async def _on_logtostderr_change(e):
        state.logtostderr = e.control.value
        await services.storage.set(
            constants.STORAGE_LOGTOSTDERR, str(e.control.value).lower()
        )

    return section_card(
        "Advanced Developer Settings",
        ft.Icons.CODE_ROUNDED,
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "Log to Stderr",
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                ),
                                tip_text(
                                    "Debug: route all CLI subprocess output directly to stderr"
                                ),
                            ],
                            spacing=tokens.SPACE_XXS,
                            expand=True,
                        ),
                        ft.Switch(
                            value=state.logtostderr,
                            on_change=lambda e: page.run_task(
                                _on_logtostderr_change, e
                            ),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        page=page,
    )
