"""Hardware defaults settings section."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.styles import glass_card, section_header, tip_text


def build_hardware_section(page: ft.Page, state, services) -> ft.Column:
    async def _on_gpu_change(e):
        state.default_gpu = e.control.value or ""
        await services.storage.set(constants.STORAGE_DEFAULT_GPU, state.default_gpu)

    async def _on_tpu_change(e):
        state.default_tpu = e.control.value or ""
        await services.storage.set(constants.STORAGE_DEFAULT_TPU, state.default_tpu)

    async def _on_timeout_change(e):
        try:
            val = int(e.control.value)
            state.default_timeout = val
            await services.storage.set(constants.STORAGE_DEFAULT_TIMEOUT, str(val))
        except (ValueError, TypeError):
            pass

    gpu_options = [ft.dropdown.Option("", "None")] + [
        ft.dropdown.Option(g, g) for g in constants.GPU_OPTIONS
    ]
    tpu_options = [ft.dropdown.Option("", "None")] + [
        ft.dropdown.Option(t, t) for t in constants.TPU_OPTIONS
    ]

    return ft.Column(
        controls=[
            section_header("HARDWARE DEFAULTS"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Dropdown(
                            label="Default GPU",
                            options=gpu_options,
                            value=state.default_gpu or "",
                            border_radius=tokens.RADIUS_MD,
                            on_select=lambda e: page.run_task(_on_gpu_change, e),
                        ),
                        tip_text("Default GPU accelerator for new sessions"),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.Dropdown(
                            label="Default TPU",
                            options=tpu_options,
                            value=state.default_tpu or "",
                            border_radius=tokens.RADIUS_MD,
                            on_select=lambda e: page.run_task(_on_tpu_change, e),
                        ),
                        tip_text("Default TPU accelerator for new sessions"),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.TextField(
                            label="Execution Timeout (seconds)",
                            value=str(state.default_timeout),
                            prefix_icon=ft.Icons.TIMER_ROUNDED,
                            keyboard_type=ft.KeyboardType.NUMBER,
                            border_radius=tokens.RADIUS_MD,
                            text_size=tokens.FONT_SM,
                            on_blur=lambda e: page.run_task(_on_timeout_change, e),
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG,
                    tokens.SPACE_XS,
                    tokens.SPACE_LG,
                    tokens.SPACE_XS,
                ),
            ),
        ],
        spacing=0,
    )
