"""Hardware defaults settings section."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.styles import section_card, tip_text


def build_hardware_section(page: ft.Page, state, services) -> ft.Container:
    async def _on_gpu_default(e):
        state.default_gpu = e.control.value or ""
        await services.storage.set(constants.STORAGE_DEFAULT_GPU, state.default_gpu)

    async def _on_tpu_default(e):
        state.default_tpu = e.control.value or ""
        await services.storage.set(constants.STORAGE_DEFAULT_TPU, state.default_tpu)

    return section_card(
        "Hardware Defaults",
        ft.Icons.MEMORY_ROUNDED,
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.MEMORY_ROUNDED,
                            size=tokens.ICON_LG,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "Default GPU",
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                ),
                                tip_text("Pre-selected GPU when creating new sessions"),
                            ],
                            spacing=tokens.SPACE_XXS,
                            expand=True,
                        ),
                        ft.Dropdown(
                            value=state.default_gpu or "",
                            options=[
                                ft.dropdown.Option("", "None (CPU)"),
                                ft.dropdown.Option("T4", "T4 · Free"),
                                ft.dropdown.Option("L4", "L4 · Pro"),
                                ft.dropdown.Option("G4", "G4 · Pro"),
                                ft.dropdown.Option("A100", "A100 · Pro+"),
                                ft.dropdown.Option("H100", "H100 · Pro+"),
                            ],
                            width=tokens.INPUT_WIDTH_LG,
                            border_radius=tokens.RADIUS_MD,
                            text_size=tokens.FONT_SM,
                            on_change=lambda e: page.run_task(_on_gpu_default, e),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=tokens.SPACE_LG,
                ),
                ft.Divider(
                    height=1,
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_CONTAINER, ft.Colors.ON_SURFACE
                    ),
                ),
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.BOLT_ROUNDED,
                            size=tokens.ICON_LG,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "Default TPU",
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                ),
                                tip_text("Pre-selected TPU when creating new sessions"),
                            ],
                            spacing=tokens.SPACE_XXS,
                            expand=True,
                        ),
                        ft.Dropdown(
                            value=state.default_tpu or "",
                            options=[
                                ft.dropdown.Option("", "None"),
                                ft.dropdown.Option("v5e1", "v5e1 · Free"),
                                ft.dropdown.Option("v6e1", "v6e1 · Free"),
                            ],
                            width=tokens.INPUT_WIDTH_LG,
                            border_radius=tokens.RADIUS_MD,
                            text_size=tokens.FONT_SM,
                            on_change=lambda e: page.run_task(_on_tpu_default, e),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=tokens.SPACE_LG,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        page=page,
    )
