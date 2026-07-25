import flet as ft

from core import constants, tokens
from core.styles import glass_card, section_header, tip_text


def build_hardware_section(page: ft.Page, state, storage):
    async def _on_gpu_default(e):
        state.default_gpu = e.control.value or ""
        await storage.set(constants.STORAGE_DEFAULT_GPU, state.default_gpu)

    async def _on_tpu_default(e):
        state.default_tpu = e.control.value or ""
        await storage.set(constants.STORAGE_DEFAULT_TPU, state.default_tpu)

    hardware_section = ft.Column(
        controls=[
            section_header("HARDWARE DEFAULTS"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.DEVELOPER_BOARD_ROUNDED,
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
                                        tip_text(
                                            "Pre-selected GPU when creating new sessions"
                                        ),
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
                                    on_select=lambda e: page.run_task(
                                        _on_gpu_default, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
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
                                        tip_text(
                                            "Pre-selected TPU when creating new sessions"
                                        ),
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
                                    on_select=lambda e: page.run_task(
                                        _on_tpu_default, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                    ],
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )
    return hardware_section


def build_execution_section(page: ft.Page, state, storage):
    async def _on_timeout_change(e):
        state.default_timeout = int(e.control.value)
        await storage.set(constants.STORAGE_DEFAULT_TIMEOUT, state.default_timeout)

    async def _on_log_format_change(e):
        state.default_log_format = e.control.value
        await storage.set(constants.STORAGE_LOG_FORMAT, state.default_log_format)

    execution_section = ft.Column(
        controls=[
            section_header("EXECUTION"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.TIMER_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Default Timeout",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(constants.TIP_TIMEOUT),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Dropdown(
                                    value=str(state.default_timeout),
                                    options=[
                                        ft.dropdown.Option(str(t), f"{t}s")
                                        for t in constants.TIMEOUT_OPTIONS
                                    ],
                                    width=tokens.INPUT_WIDTH_SM,
                                    border_radius=tokens.RADIUS_MD,
                                    text_size=tokens.FONT_SM,
                                    on_select=lambda e: page.run_task(
                                        _on_timeout_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.SAVE_ALT_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Log Export Format",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Default format when exporting session logs"
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Dropdown(
                                    value=state.default_log_format,
                                    options=[
                                        ft.dropdown.Option("ipynb", ".ipynb"),
                                        ft.dropdown.Option("md", ".md"),
                                        ft.dropdown.Option("jsonl", ".jsonl"),
                                        ft.dropdown.Option("txt", ".txt"),
                                    ],
                                    width=tokens.INPUT_WIDTH_SM,
                                    border_radius=tokens.RADIUS_MD,
                                    text_size=tokens.FONT_SM,
                                    on_select=lambda e: page.run_task(
                                        _on_log_format_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                    ],
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )
    return execution_section
