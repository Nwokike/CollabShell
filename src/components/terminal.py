"""Terminal component — adapted from SpanInsight's build_terminal."""

import flet as ft

from core import tokens
from core.theme import AppColors


def build_terminal(
    code: str = "",
    on_run=None,
    on_clear=None,
    filename: str = "colab.py",
    is_running: bool = False,
    field_ref=None,
) -> ft.Container:
    """Build a macOS-style terminal component with code input and run button.

    Adapted from SpanInsight's build_terminal:
    - macOS-style title bar with red/yellow/green dots
    - Multiline code input with monospace font
    - Run button in the title bar
    """
    # Title bar with macOS dots + filename + run button
    title_bar = ft.Container(
        content=ft.Row(
            controls=[
                # macOS dots
                ft.Row(
                    controls=[
                        ft.Container(
                            width=12,
                            height=12,
                            border_radius=6,
                            bgcolor=AppColors.TERMINAL_DOT_RED,
                        ),
                        ft.Container(
                            width=12,
                            height=12,
                            border_radius=6,
                            bgcolor=AppColors.TERMINAL_DOT_YELLOW,
                        ),
                        ft.Container(
                            width=12,
                            height=12,
                            border_radius=6,
                            bgcolor=AppColors.TERMINAL_DOT_GREEN,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                # Filename
                ft.Text(
                    filename,
                    size=tokens.FONT_SM,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
                    expand=True,
                    text_align=ft.TextAlign.CENTER,
                ),
                # Run / Stop button
                ft.IconButton(
                    icon=ft.Icons.STOP_ROUNDED
                    if is_running
                    else ft.Icons.PLAY_ARROW_ROUNDED,
                    icon_color=AppColors.TERMINAL_DOT_GREEN
                    if not is_running
                    else AppColors.TERMINAL_DOT_RED,
                    icon_size=tokens.ICON_LG,
                    on_click=on_run,
                    tooltip="Stop" if is_running else "Run",
                )
                if not is_running
                else ft.Row(
                    controls=[
                        ft.ProgressRing(
                            width=18,
                            height=18,
                            stroke_width=2,
                            color=AppColors.TERMINAL_DOT_GREEN,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.STOP_ROUNDED,
                            icon_color=AppColors.TERMINAL_DOT_RED,
                            icon_size=tokens.ICON_LG,
                            on_click=on_clear,
                            tooltip="Stop",
                        ),
                    ],
                    spacing=tokens.SPACE_XS,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=AppColors.TERMINAL_HEADER,
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_SM, tokens.SPACE_SM
        ),
        border_radius=ft.BorderRadius(tokens.RADIUS_MD, tokens.RADIUS_MD, 0, 0),
    )

    # Code input area
    code_input = ft.TextField(
        ref=field_ref,
        value=code,
        multiline=True,
        min_lines=4,
        max_lines=12,
        filled=True,
        fill_color=AppColors.TERMINAL_BG,
        color=AppColors.DARK_TEXT,
        cursor_color=AppColors.TERMINAL_CURSOR,
        border_width=0,
        text_size=tokens.FONT_SM,
        text_style=ft.TextStyle(font_family="RobotoMono"),
        hint_text="# Type your Python code here...\nprint('Hello from Colab!')",
        hint_style=ft.TextStyle(
            color=ft.Colors.with_opacity(0.3, ft.Colors.WHITE),
            font_family="RobotoMono",
            size=tokens.FONT_SM,
        ),
        content_padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_MD, tokens.SPACE_MD, tokens.SPACE_MD
        ),
        border_radius=ft.BorderRadius(0, 0, tokens.RADIUS_MD, tokens.RADIUS_MD),
    )

    return ft.Container(
        content=ft.Column(
            controls=[title_bar, code_input],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        border_radius=tokens.RADIUS_MD,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.2, ft.Colors.WHITE)),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )
