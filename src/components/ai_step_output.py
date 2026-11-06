"""AI step output — the notebook's own output widget, verbatim.

A tool step (run code, read terminal, …) renders its output in the SAME
panel the notebook uses: same ANSI renderer, same terminal background, same
Copy Output button. Open Notebook / Open Terminal actions are removed
pending the assistant-notebook redesign (they opened the wrong screen and
showed an empty notebook).
"""

from __future__ import annotations

import flet as ft

from components.ansi_parser import parse_ansi_to_flet_text
from components.notebook_cell.output import parse_outputs_to_controls
from core import tokens
from core.theme import AppColors


def _copyable_text(outputs: list) -> str:
    """The text Copy Output would actually put on the clipboard.

    Mirrors notebook_cell.actions.copy_output's extraction so the button can
    appear ONLY when there is something copyable — never on an empty or
    placeholder ('None') output.
    """
    import re

    parts: list[str] = []
    for out in outputs or []:
        if isinstance(out, str):
            parts.append(out)
            continue
        if not isinstance(out, dict):
            continue
        if out.get("type") == "error":
            parts.append("\n".join(str(t) for t in out.get("traceback", []) or []))
            continue
        text = out.get("text")
        if text is None:
            data = out.get("data") or {}
            if isinstance(data, dict):
                plain = data.get("text/plain")
                if isinstance(plain, list):
                    plain = "".join(str(p) for p in plain)
                text = plain
        if text is not None:
            parts.append(str(text))
    joined = "\n".join(parts)
    # Strip ANSI escapes the same way copy_output does, then judge.
    stripped = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", joined)
    return stripped.strip()


def _output_panel(
    output_controls: list,
    action_buttons: list,
    *,
    fallback_text: str = "",
) -> ft.Control:
    """The notebook's output panel, verbatim shape.

    Same terminal background, same dynamic 36..220px height, same actions row.
    """
    if not output_controls and fallback_text.strip():
        output_controls = [
            parse_ansi_to_flet_text(raw_text=fallback_text, default_size=tokens.FONT_SM)
        ]

    # Dynamic height exactly like the notebook cell: the ANSI parser emits
    # ft.Text(spans=...) with an empty value, so count newlines across spans.
    line_count = 0
    for ctrl in output_controls:
        text = getattr(ctrl, "value", "") or ""
        if not text:
            text = "".join(
                getattr(span, "text", "") or ""
                for span in (getattr(ctrl, "spans", None) or [])
            )
        line_count += max(text.count("\n") + 1, 1)
    calc_height = min(max(line_count * 20 + 16, 36), 220) if output_controls else None

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.ListView(
                    controls=output_controls,
                    spacing=tokens.SPACE_XXS,
                    auto_scroll=True,
                    height=calc_height,
                    expand=False,
                ),
                (
                    ft.Row(
                        controls=action_buttons,
                        spacing=0,
                        alignment=ft.MainAxisAlignment.END,
                    )
                    if action_buttons
                    else ft.Container()
                ),
            ],
            spacing=tokens.SPACE_XXS,
        ),
        padding=tokens.SPACE_SM,
        bgcolor=AppColors.TERMINAL_BG,
        border_radius=tokens.RADIUS_SM,
        visible=bool(output_controls),
        width=float("inf"),
    )


def build_ai_step_output(
    tool_name: str,
    outputs: list,
    state: str,  # "running" | "done" | "error"
    *,
    fallback_text: str = "",
    page=None,
) -> ft.Control:
    """The notebook output widget for one tool step.

    Args:
        tool_name: The tool that produced this output (_exec, read_terminal, …)
        outputs: Output dicts in the notebook cell shape.
        state: Current step state ("running", "done", "error").
        fallback_text: Shown through the same ANSI renderer when the tool
            produced no structured outputs (e.g. the streamed live text).
        page: The page, so Copy uses the notebook's own copy_output helper.
    """
    output_controls = parse_outputs_to_controls(outputs)

    action_buttons: list = []
    # The notebook's own Copy Output button — ONLY when there is something
    # copyable (never over a "None idle" placeholder).
    if page is not None and _copyable_text(outputs):
        from components.notebook_cell.actions import copy_output

        async def _copy_output(e=None):
            await copy_output(page, list(outputs))

        action_buttons.append(
            ft.IconButton(
                ft.Icons.COPY_ALL_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Copy Output",
                on_click=lambda e: page.run_task(_copy_output, e),
            )
        )

    panel = _output_panel(output_controls, action_buttons, fallback_text=fallback_text)
    return ft.Container(
        content=panel,
        padding=ft.Padding.only(left=tokens.SPACE_MD),
        margin=ft.Margin(0, 0, 0, tokens.SPACE_SM),
    )


def build_live_tool_output(
    tool_name: str,
    text: str,
    *,
    page=None,
) -> ft.Control:
    """Live streaming panel for a running tool — the same output panel."""
    panel = _output_panel([], [], fallback_text=text)
    return ft.Container(
        content=panel,
        padding=ft.Padding.only(left=tokens.SPACE_MD),
    )
