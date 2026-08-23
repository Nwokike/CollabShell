"""Notebook cell — declarative component built on Flet 0.86.x observables.

`CellData` is an @ft.observable model. Mutating any field (source, outputs,
is_running, is_editing) notifies subscribers, and the `NotebookCell`
component re-renders itself automatically — no refs, no frozen-control
mutation, no manual page.update().
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import flet as ft

from components.notebook_cell.actions import copy_code, copy_output, make_actions_row
from components.notebook_cell.output import parse_outputs_to_controls
from core import tokens
from core.theme import AppColors


@ft.observable
class CellData:
    """Observable notebook cell model (code or markdown)."""

    def __init__(
        self,
        cell_id: str | None = None,
        cell_type: str = "code",
        source: str = "",
        outputs: list | None = None,
        is_running: bool = False,
        is_editing: bool | None = None,
    ):
        self.id = cell_id or str(uuid.uuid4())
        self.type = cell_type
        self.source = source
        self.outputs = list(outputs or [])  # wrapped as ObservableList
        self.is_running = is_running
        # Bumped on every outputs mutation so use_memo can re-parse cheaply
        self.outputs_rev = 0
        # Markdown cells start in edit mode when empty
        self.is_editing = (
            (not bool(source.strip())) if is_editing is None else is_editing
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "outputs": list(self.outputs),
            "is_running": False,
            "is_editing": self.is_editing,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CellData:
        return cls(
            cell_id=d.get("id"),
            cell_type=d.get("type", "code"),
            source=d.get("source", ""),
            outputs=d.get("outputs", []),
            is_running=False,
            is_editing=d.get("is_editing"),
        )


@ft.component
def NotebookCell(
    cell: CellData,
    on_run: Callable[[], None] | None = None,
    on_stop: Callable[[], None] | None = None,
    on_delete: Callable[[], None] | None = None,
    on_move_up: Callable[[], None] | None = None,
    on_move_down: Callable[[], None] | None = None,
    on_source_change: Callable[[str], None] | None = None,
    on_clear_output: Callable[[], None] | None = None,
    on_open_terminal: Callable[[], None] | None = None,
    is_active: bool = False,
    on_focus_change: Callable[[str, bool], None] | None = None,
    focus_token: int = 0,
) -> ft.Control:
    """Renders one notebook cell. Re-renders reactively when `cell` changes."""
    page = ft.context.page

    # Hooks must run unconditionally in the same order on every render,
    # regardless of cell type.
    parse_cache = ft.use_ref(lambda: {"rev": -1, "count": 0, "controls": []})
    editor_ref = ft.use_ref(None)

    def _focus_effect():
        # focus_token > 0 asks this cell's editor to grab focus after render
        # (shortcut: run-and-advance, insert cell, toggle type).
        if focus_token and editor_ref.current is not None:
            try:
                page.run_task(editor_ref.current.focus)
            except RuntimeError:
                pass

    ft.use_effect(_focus_effect, [focus_token])

    def _commit_source(value: str):
        cell.source = value
        if on_source_change:
            on_source_change(value)

    def _report_focus(focused: bool):
        if on_focus_change:
            on_focus_change(cell.id, focused)

    def _finish_markdown_edit(value: str | None = None):
        """Commit the latest text and render — used by Done and on_blur so
        tapping into another cell auto-renders without pressing Done."""
        if value is not None:
            _commit_source(value)
        cell.is_editing = False

    async def _copy_output_task(e=None):
        await copy_output(page, list(cell.outputs))

    async def _copy_code_task(e=None):
        await copy_code(page, cell.source)

    def _make_actions_row():
        return make_actions_row(
            on_move_up=on_move_up,
            on_move_down=on_move_down,
            on_delete=on_delete,
            on_copy=lambda: page.run_task(_copy_code_task),
        )

    # ── Markdown cell ─────────────────────────────────────────────────────────
    if cell.type == "markdown":
        if cell.is_editing:
            content = ft.Column(
                controls=[
                    ft.TextField(
                        value=cell.source,
                        multiline=True,
                        min_lines=2,
                        max_lines=8,
                        text_size=tokens.FONT_SM,
                        border_color=ft.Colors.TRANSPARENT,
                        bgcolor=ft.Colors.TRANSPARENT,
                        ref=editor_ref,
                        on_focus=lambda e: _report_focus(True),
                        on_blur=lambda e: (
                            _finish_markdown_edit(e.control.value or ""),
                            _report_focus(False),
                        ),
                        on_change=lambda e: _commit_source(e.control.value or ""),
                        hint_text="Type markdown here...",
                        content_padding=tokens.SPACE_SM,
                        expand=True,
                    ),
                    ft.Row(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Icon(
                                        ft.Icons.MODE_EDIT_OUTLINE_ROUNDED,
                                        size=tokens.FONT_MD,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                    ft.Text(
                                        "Markdown",
                                        size=tokens.FONT_XS,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                ],
                                spacing=tokens.SPACE_XS,
                            ),
                            ft.Container(expand=True),
                            ft.IconButton(
                                icon=ft.Icons.CHECK_ROUNDED,
                                icon_size=tokens.ICON_SM,
                                icon_color=AppColors.SUCCESS,
                                tooltip="Done / Render Markdown",
                                on_click=lambda e: _finish_markdown_edit(),
                            ),
                            _make_actions_row(),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=0,
            )
        else:
            content = ft.Column(
                controls=[
                    ft.GestureDetector(
                        on_tap=lambda e: setattr(cell, "is_editing", True),
                        content=ft.Container(
                            content=ft.Markdown(
                                value=cell.source,
                                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                                selectable=True,
                                on_tap_link=lambda e: page.run_task(
                                    ft.UrlLauncher().launch_url, e.data
                                ),
                            ),
                            padding=tokens.SPACE_SM,
                            expand=True,
                            width=float("inf"),
                        ),
                    ),
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Container(expand=True),
                                ft.IconButton(
                                    ft.Icons.EDIT_ROUNDED,
                                    icon_size=tokens.ICON_SM,
                                    tooltip="Edit Markdown",
                                    on_click=lambda e: setattr(
                                        cell, "is_editing", True
                                    ),
                                ),
                                _make_actions_row(),
                            ],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                        padding=ft.Padding(
                            tokens.SPACE_SM, 0, tokens.SPACE_SM, tokens.SPACE_SM
                        ),
                    ),
                ],
                spacing=0,
            )

        return ft.Container(
            content=content,
            border_radius=tokens.RADIUS_MD,
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
            border=(
                ft.Border(left=ft.BorderSide(3, ft.Colors.PRIMARY))
                if is_active
                else ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE))
            ),
            margin=ft.Margin(0, tokens.SPACE_SM, 0, tokens.SPACE_SM),
        )

    # ── Code cell ─────────────────────────────────────────────────────────────
    # Incremental output parsing: only new entries are converted to controls on
    # each streaming chunk (O(new) instead of re-parsing the whole stream).
    def _get_output_controls() -> list[ft.Control]:
        cache = parse_cache.current
        if cache["rev"] != cell.outputs_rev:
            outs = list(cell.outputs)
            if len(outs) <= cache["count"] and cache["rev"] != -1:
                # Cleared, truncated, or capped rotation — full re-parse
                cache["controls"] = parse_outputs_to_controls(outs)[:1000]
                cache["count"] = len(outs)
            else:
                new_entries = outs[cache["count"] :]
                room = 1000 - len(cache["controls"])
                if new_entries and room > 0:
                    cache["controls"].extend(
                        parse_outputs_to_controls(new_entries)[:room]
                    )
                cache["count"] = len(outs)
            cache["rev"] = cell.outputs_rev
        # Always hand the reconciler a FRESH list. The previously rendered
        # (frozen) ListView still references the cached list; mutating it in
        # place would make old == new in the diff and new output would never
        # paint (the "invisible until remount" bug).
        return list(cache["controls"])

    output_controls = _get_output_controls()

    # Dynamic height for compact output boxes (legacy behavior: 36..220px).
    # The ANSI parser emits ft.Text(spans=...) with value=None, so count
    # newlines across the spans' text instead of ctrl.value.
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

    output_actions = ft.Row(
        controls=[
            ft.Text(
                "OUTPUT",
                size=tokens.FONT_XXS,
                color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                weight=ft.FontWeight.W_600,
            ),
            ft.Row(
                controls=[
                    ft.IconButton(
                        ft.Icons.TERMINAL_ROUNDED,
                        icon_size=tokens.ICON_SM,
                        tooltip="Open Real Terminal",
                        on_click=lambda e: (
                            on_open_terminal() if on_open_terminal else None
                        ),
                    ),
                    ft.IconButton(
                        ft.Icons.COPY_ALL_ROUNDED,
                        icon_size=tokens.ICON_SM,
                        tooltip="Copy Output",
                        on_click=lambda e: page.run_task(_copy_output_task, e),
                    ),
                    ft.IconButton(
                        ft.Icons.CLEAR_ALL_ROUNDED,
                        icon_size=tokens.ICON_SM,
                        tooltip="Clear Output",
                        on_click=lambda e: (
                            on_clear_output() if on_clear_output else None
                        ),
                    ),
                ],
                spacing=0,
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    output_panel = ft.Container(
        content=ft.Column(
            controls=[
                ft.ListView(
                    controls=output_controls,
                    spacing=tokens.SPACE_XXS,
                    auto_scroll=True,
                    height=calc_height,
                    expand=False,
                ),
                output_actions,
            ],
            spacing=tokens.SPACE_XXS,
        ),
        padding=tokens.SPACE_SM,
        bgcolor=AppColors.TERMINAL_BG,
        border_radius=tokens.RADIUS_SM,
        visible=bool(output_controls) or cell.is_running,
        width=float("inf"),
    )

    editor_box = ft.Container(
        content=ft.Column(
            controls=[
                ft.TextField(
                    value=cell.source,
                    multiline=True,
                    min_lines=1,
                    max_lines=10,
                    text_style=ft.TextStyle(
                        font_family="RobotoMono", size=tokens.FONT_SM
                    ),
                    border_color=ft.Colors.TRANSPARENT,
                    bgcolor=ft.Colors.TRANSPARENT,
                    ref=editor_ref,
                    on_focus=lambda e: _report_focus(True),
                    on_blur=lambda e: _report_focus(False),
                    on_change=lambda e: _commit_source(e.control.value or ""),
                    hint_text=(
                        "Write Python code here.\nPrefix with ! to run a terminal"
                        " command\ne.g. !pip install requests"
                    ),
                    content_padding=tokens.SPACE_SM,
                    expand=True,
                ),
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.IconButton(
                                ft.Icons.PLAY_ARROW_ROUNDED,
                                icon_size=tokens.ICON_MD,
                                icon_color=AppColors.SUCCESS,
                                on_click=lambda e: on_run() if on_run else None,
                                tooltip="Run Cell",
                                visible=not cell.is_running,
                            ),
                            ft.Row(
                                controls=[
                                    ft.ProgressRing(
                                        width=tokens.ICON_SM,
                                        height=tokens.ICON_SM,
                                        stroke_width=2,
                                    ),
                                    ft.IconButton(
                                        ft.Icons.STOP_ROUNDED,
                                        icon_size=tokens.ICON_SM,
                                        icon_color=AppColors.ERROR,
                                        on_click=lambda e: (
                                            on_stop() if on_stop else None
                                        ),
                                        tooltip="Stop",
                                    ),
                                ],
                                spacing=tokens.SPACE_XS,
                                visible=cell.is_running,
                            ),
                            ft.Container(expand=True),
                            _make_actions_row(),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_XS, 0, tokens.SPACE_SM, tokens.SPACE_XS
                    ),
                ),
            ],
            spacing=0,
        ),
        border_radius=tokens.RADIUS_SM,
        bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
    )

    return ft.Container(
        content=ft.Column(
            controls=[
                editor_box,
                ft.Container(
                    content=output_panel,
                    padding=ft.Padding(0, tokens.SPACE_XS, 0, 0),
                ),
            ],
            spacing=0,
        ),
        padding=tokens.SPACE_SM,
        border=ft.Border(
            left=ft.BorderSide(
                3,
                ft.Colors.PRIMARY
                if is_active
                else ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE),
            ),
        ),
        margin=ft.Margin(0, tokens.SPACE_SM, 0, tokens.SPACE_SM),
    )


__all__ = ["CellData", "NotebookCell"]
