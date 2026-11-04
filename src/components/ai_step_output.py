"""AI step output — the notebook's own output widget, verbatim.

A tool step (run code, read terminal, …) renders its output in the SAME
panel the notebook uses (same ANSI renderer, same terminal background, same
Copy Output button), minus the Clear/Real-Terminal actions, plus one Open
action: Open Notebook or Open Terminal, matching the session's current view.
The owner's model is DDGS's search step: you SEE what the assistant sees,
then click through to the live surface.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from components.ansi_parser import parse_ansi_to_flet_text
from components.notebook_cell.output import parse_outputs_to_controls
from core import tokens
from core.theme import AppColors

_OPENABLE_TOOLS = {
    "_exec",
    "read_terminal",
    "read_notebook",
    "write_cells",
    "read_file",
    "list_files",
    "upload_file",
    "install_package",
}


def _open_action_buttons(
    tool_name: str,
    state: str,
    session_mode: str,
    on_open_terminal: Callable[[], None] | None,
    on_open_notebook: Callable[[], None] | None,
) -> list:
    """[Open Notebook | Open Terminal] for an openable tool.

    The target follows WHAT the tool did, not the current view: _exec and the
    file/notebook tools speak the session KERNEL, which is the notebook's
    world; only read_terminal is a shell thing. The current view breaks ties.
    """
    if state not in ("running", "done") or tool_name not in _OPENABLE_TOOLS:
        return []
    if tool_name == "read_terminal":
        target = "terminal"
    elif tool_name in ("_exec", "read_notebook", "write_cells", "install_package"):
        target = "notebook"
    else:
        target = session_mode if session_mode in ("notebook", "terminal") else "notebook"
    # The label is TEXT, not just an icon — "Open Notebook" vs "Open Terminal"
    # must be readable at a glance.
    if target == "notebook" and on_open_notebook is not None:
        return [
            ft.TextButton(
                "Open Notebook",
                icon=ft.Icons.DESCRIPTION_ROUNDED,
                on_click=lambda e: on_open_notebook(),
                style=ft.ButtonStyle(padding=ft.Padding(4, 2, 4, 2)),
            )
        ]
    if on_open_terminal is not None:
        return [
            ft.TextButton(
                "Open Terminal",
                icon=ft.Icons.TERMINAL_ROUNDED,
                on_click=lambda e: on_open_terminal(),
                style=ft.ButtonStyle(padding=ft.Padding(4, 2, 4, 2)),
            )
        ]
    return []


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
    session_mode: str = "",
    fallback_text: str = "",
    page=None,
    on_open_terminal: Callable[[], None] | None = None,
    on_open_notebook: Callable[[], None] | None = None,
) -> ft.Control:
    """The notebook output widget for one tool step.

    Args:
        tool_name: The tool that produced this output (_exec, read_terminal, …)
        outputs: Output dicts in the notebook cell shape.
        state: Current step state ("running", "done", "error").
        session_mode: The session's current view ("notebook"/"terminal"/"files")
            — picks the Open action target.
        fallback_text: Shown through the same ANSI renderer when the tool
            produced no structured outputs (e.g. the streamed live text).
        page: The page, so Copy uses the notebook's own copy_output helper.
        on_open_terminal / on_open_notebook: Open actions.
    """
    output_controls = parse_outputs_to_controls(outputs)

    action_buttons = _open_action_buttons(
        tool_name, state, session_mode, on_open_terminal, on_open_notebook
    )
    # The notebook's own Copy Output button (same helper, same icon) — but
    # ONLY when there is something copyable: a button that copies nothing (or
    # copies the string "None") is worse than no button.
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
    session_mode: str = "",
    page=None,
    on_open_terminal: Callable[[], None] | None = None,
    on_open_notebook: Callable[[], None] | None = None,
) -> ft.Control:
    """Live streaming panel for a running tool — the same output panel."""
    action_buttons = _open_action_buttons(
        tool_name, "running", session_mode, on_open_terminal, on_open_notebook
    )
    panel = _output_panel(
        [], action_buttons, fallback_text=text
    )
    return ft.Container(
        content=panel,
        padding=ft.Padding.only(left=tokens.SPACE_MD),
    )
