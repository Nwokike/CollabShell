"""Output panel — scrollable streaming output display."""

import flet as ft

from core import tokens
from core.theme import AppColors
from components.ansi_parser import parse_ansi_to_flet_text


def build_output_panel(
    list_ref: ft.Ref[ft.ListView] = None,
    lines: list = None,
    is_visible: bool = True,
    on_clear=None,
) -> ft.Container:
    """Build a scrollable output panel for streaming execution results.

    - Auto-scroll ListView with monospace text
    - Clear button
    - Dark background matching terminal
    """
    if not is_visible:
        return ft.Container(width=0, height=0)

    output_lines = lines or []

    output_controls = []
    for line in output_lines:
        is_error = (
            line.startswith("Error") or line.startswith("Traceback") or "Error:" in line
        )
        
        output_controls.append(
            parse_ansi_to_flet_text(
                raw_text=line,
                default_size=tokens.FONT_SM,
                is_error=is_error
            )
        )

    if not output_controls:
        output_controls.append(
            ft.Text(
                "Output will appear here...",
                size=tokens.FONT_SM,
                color=ft.Colors.with_opacity(0.3, "#FFFFFF"),
                font_family="RobotoMono",
                italic=True,
            )
        )

    async def _on_copy(e):
        text_to_copy = "\n".join(output_lines)
        if text_to_copy and e.control.page:
            await e.control.page.clipboard.set(text_to_copy)
            e.control.page.snack_bar = ft.SnackBar(ft.Text("Output copied to clipboard!"))
            e.control.page.snack_bar.open = True
            e.control.page.update()

    header = ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.TERMINAL_ROUNDED,
                    size=tokens.ICON_SM,
                    color=ft.Colors.with_opacity(0.5, "#FFFFFF"),
                ),
                ft.Text(
                    "OUTPUT",
                    size=tokens.FONT_XXS,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.with_opacity(0.5, "#FFFFFF"),
                    style=ft.TextStyle(letter_spacing=1),
                    expand=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.CONTENT_COPY_ROUNDED,
                    icon_size=tokens.ICON_SM,
                    icon_color=ft.Colors.with_opacity(0.5, "#FFFFFF"),
                    on_click=_on_copy,
                    tooltip="Copy output",
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                    icon_size=tokens.ICON_SM,
                    icon_color=ft.Colors.with_opacity(0.5, "#FFFFFF"),
                    on_click=on_clear,
                    tooltip="Clear output",
                )
                if on_clear
                else ft.Container(width=0),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_SM, tokens.SPACE_SM
        ),
    )

    output_list = ft.ListView(
        ref=list_ref,
        controls=output_controls,
        spacing=tokens.SPACE_XXS,
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_MD
        ),
        auto_scroll=True,
        height=200,
    )

    return ft.Container(
        content=ft.Column(
            controls=[output_list, header],
            spacing=0,
        ),
        bgcolor=AppColors.TERMINAL_BG,
        border_radius=tokens.RADIUS_MD,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.15, "#FFFFFF")),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )
