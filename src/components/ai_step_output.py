"""Shared AI step output rendering — reuses notebook cell output components.

This component renders tool output (from _exec, read_terminal, read_notebook, etc.)
with the same rich formatting as notebook cells: ANSI parsing, images, copy button,
and action buttons (Open Terminal, Open Notebook).
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from components.notebook_cell.output import parse_outputs_to_controls
from core import tokens
from core.theme import AppColors


def build_ai_step_output(
    tool_name: str,
    outputs: list,
    state: str,  # "running" | "done" | "error"
    on_open_terminal: Callable[[], None] | None = None,
    on_open_notebook: Callable[[], None] | None = None,
    on_copy: Callable[[], None] | None = None,
) -> ft.Control:
    """Build a rich output panel for an AI step row.

    Args:
        tool_name: The tool that produced this output (_exec, read_terminal, etc.)
        outputs: List of output dicts (same format as notebook cell outputs)
        state: Current state of the step ("running", "done", "error")
        on_open_terminal: Callback to open terminal tab
        on_open_notebook: Callback to open notebook tab
        on_copy: Callback to copy output to clipboard

    Returns:
        A Flet Control rendering the output with actions.
    """
    # Parse outputs using the same logic as notebook cells
    output_controls = parse_outputs_to_controls(outputs)

    # Build action buttons based on tool and state
    action_buttons = []

    if tool_name == "_exec" and state in ("running", "done") or tool_name == "read_terminal" and state in ("running", "done"):
        action_buttons.append(
            ft.TextButton(
                "Open Terminal",
                icon=ft.Icons.TERMINAL_ROUNDED,
                on_click=lambda e: on_open_terminal() if on_open_terminal else None,
                style=ft.ButtonStyle(padding=ft.Padding(4, 2, 4, 2)),
            )
        )
    elif tool_name == "read_notebook" and state in ("running", "done"):
        action_buttons.append(
            ft.TextButton(
                "Open Notebook",
                icon=ft.Icons.DESCRIPTION_ROUNDED,
                on_click=lambda e: on_open_notebook() if on_open_notebook else None,
                style=ft.ButtonStyle(padding=ft.Padding(4, 2, 4, 2)),
            )
        )

    if on_copy:
        action_buttons.append(
            ft.TextButton(
                "Copy",
                icon=ft.Icons.COPY_ROUNDED,
                on_click=lambda e: on_copy() if on_copy else None,
                style=ft.ButtonStyle(padding=ft.Padding(4, 2, 4, 2)),
            )
        )

    # Build the output panel
    content = ft.Column(
        controls=[
            ft.Container(
                content=ft.Column(
                    controls=output_controls,
                    spacing=tokens.SPACE_XS,
                    scroll=ft.ScrollMode.AUTO,
                ),
                bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
                padding=tokens.SPACE_SM,
                border_radius=tokens.RADIUS_SM,
                expand=True,
            ),
            ft.Row(
                controls=action_buttons,
                spacing=tokens.SPACE_XS,
                alignment=ft.MainAxisAlignment.END,
            ) if action_buttons else ft.Container(),
        ],
        spacing=tokens.SPACE_XXS,
        tight=True,
    )

    return ft.Container(
        content=content,
        padding=ft.Padding.only(left=tokens.SPACE_MD),
        border=ft.Border(
            left=ft.BorderSide(
                3,
                AppColors.SUCCESS if state == "done" else
                AppColors.ERROR if state == "error" else
                ft.Colors.PRIMARY,
            ),
        ),
        margin=ft.Margin(0, tokens.SPACE_SM, 0, tokens.SPACE_SM),
    )


def build_live_tool_output(
    tool_name: str,
    text: str,
    on_open_terminal: Callable[[], None] | None = None,
    on_open_notebook: Callable[[], None] | None = None,
) -> ft.Control:
    """Build a live streaming output panel for a running tool.

    Simpler version for real-time streaming output.
    """
    action_buttons = []

    if tool_name in ("_exec", "read_terminal"):
        action_buttons.append(
            ft.TextButton(
                "Open Terminal",
                icon=ft.Icons.TERMINAL_ROUNDED,
                on_click=lambda e: on_open_terminal() if on_open_terminal else None,
                style=ft.ButtonStyle(padding=ft.Padding(4, 2, 4, 2)),
            )
        )
    elif tool_name == "read_notebook":
        action_buttons.append(
            ft.TextButton(
                "Open Notebook",
                icon=ft.Icons.DESCRIPTION_ROUNDED,
                on_click=lambda e: on_open_notebook() if on_open_notebook else None,
                style=ft.ButtonStyle(padding=ft.Padding(4, 2, 4, 2)),
            )
        )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Text(
                        text,
                        size=tokens.FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        selectable=True,
                    ),
                    bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
                    padding=tokens.SPACE_SM,
                    border_radius=tokens.RADIUS_SM,
                    expand=True,
                ),
                ft.Row(
                    controls=action_buttons,
                    spacing=tokens.SPACE_XS,
                    alignment=ft.MainAxisAlignment.END,
                ) if action_buttons else ft.Container(),
            ],
            spacing=tokens.SPACE_XXS,
            tight=True,
        ),
        padding=ft.Padding.only(left=tokens.SPACE_MD),
        border=ft.Border(
            left=ft.BorderSide(3, ft.Colors.PRIMARY),
        ),
        margin=ft.Margin(0, tokens.SPACE_SM, 0, tokens.SPACE_SM),
    )