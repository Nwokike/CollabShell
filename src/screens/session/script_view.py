"""Script view — the second renderer for a notebook tab.

A tab is one document (a cell list). Notebook view draws it as cell boxes;
this module draws the SAME cells as one plain ``# %%``-marked editor, so no
conversion happens in either direction and a toggle loses nothing.

Editing re-splits the text and merges it back through ``merge_script_cells``,
which preserves the outputs of cells the user did not touch — the naive
version would wipe every plot on the first keystroke.
"""

from __future__ import annotations

import asyncio
import logging

import flet as ft

from components.notebook_cell.output import parse_outputs_to_controls
from core import tokens
from services.ipynb_converter import block_at_offset, cells_to_py
from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx

logger = logging.getLogger("ScriptView")

_SAVE_DEBOUNCE_SEC = 1.0


@ft.component
def ScriptView(
    session_name: str,
    tab: dict,
    on_script_change=None,
    session_env_override: dict | None = None,
):
    """Render and edit a tab's cells as one script.

    ``tab`` is the live tab dict (``id``/``name``/``view``/``cells``);
    ``on_script_change(new_text)`` is called debounced with the edited script.
    """
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    text, set_text = ft.use_state(lambda: cells_to_py(tab.get("cells") or []))
    outputs, set_outputs = ft.use_state([])
    is_running, set_is_running = ft.use_state(False)
    caret, set_caret = ft.use_state(0)
    debounce_ref = ft.use_ref(None)
    # Re-seed the editor only when the TAB changes, never on every parent
    # render — overwriting the field while the user types moves the caret.
    seeded_for, set_seeded_for = ft.use_state(tab.get("id"))

    if seeded_for != tab.get("id"):
        set_seeded_for(tab.get("id"))
        set_text(cells_to_py(tab.get("cells") or []))
        set_outputs([])
        set_caret(0)

    def _flush_save():
        if debounce_ref.current is not None:
            debounce_ref.current.cancel()
            debounce_ref.current = None
        if on_script_change:
            on_script_change(text)

    ft.on_unmounted(_flush_save)

    def _on_selection_change(e):
        sel = getattr(e, "selection", None)
        if sel is not None:
            try:
                set_caret(int(sel.base_offset))
            except (TypeError, ValueError):
                pass

    def _effective_env() -> dict:
        merged = dict(getattr(state, "default_env", None) or {})
        if session_env_override:
            merged.update(session_env_override)
        return merged

    def _append_output(payload):
        entry = (
            payload
            if isinstance(payload, dict)
            else {"type": "stream", "text": str(payload)}
        )
        set_outputs(lambda prev: [*prev, entry])

    async def _run(code: str):
        set_is_running(True)
        set_outputs([])
        try:
            await services.colab.exec_code(
                code,
                session_name,
                timeout=float(state.default_timeout),
                auth_method=state.auth_method,
                on_output=_append_output,
                intercept_oauth=True,
                env=_effective_env() or None,
            )
        except Exception as exc:
            logger.warning("Script run failed: %s", exc)
            # Bind the payload before the updater: `except ... as exc` is
            # deleted when the block ends, so a closure over it would raise
            # NameError the moment it ran later.
            failure = {
                "type": "error",
                "ename": type(exc).__name__,
                "evalue": str(exc),
                "traceback": [str(exc)],
            }
            set_outputs(lambda prev: [*prev, failure])
        finally:
            set_is_running(False)

    def _run_cell(e=None):
        if is_running:
            return
        source = block_at_offset(text, caret)
        if not source.strip():
            controller.show_snack("Nothing to run in this cell.", is_error=True)
            return
        page.run_task(_run, source)

    def _run_file(e=None):
        if is_running:
            return
        from services.script_runner import build_run_file_payload

        if not (text or "").strip():
            controller.show_snack("Script is empty.", is_error=True)
            return
        page.run_task(_run, build_run_file_payload(text))

    def _emit_change():
        debounce_ref.current = None
        if on_script_change:
            on_script_change(text)

    def _on_text_change(e):
        value = e.control.value or ""
        set_text(value)
        try:
            loop = asyncio.get_running_loop()
            if debounce_ref.current is not None:
                debounce_ref.current.cancel()
            debounce_ref.current = loop.call_later(
                _SAVE_DEBOUNCE_SEC, _emit_change
            )
        except RuntimeError:
            _emit_change()

    # ── Inline output panel ────────────────────────────────────────────────
    # Rendered through the same parser the notebook cells use, so ANSI colour,
    # images, and tracebacks look identical in both views. Transient by
    # design: a script has no persisted outputs and .py cannot carry them.
    output_panel = ft.Container(
        content=ft.Column(
            controls=parse_outputs_to_controls(outputs),
            spacing=tokens.SPACE_XS,
            scroll=ft.ScrollMode.AUTO,
        ),
        bgcolor=ft.Colors.ON_SURFACE,
        padding=ft.Padding(tokens.SPACE_SM),
        border_radius=tokens.RADIUS_MD,
        visible=bool(outputs) or is_running,
    )

    editor = ft.TextField(
        value=text,
        multiline=True,
        min_lines=8,
        max_lines=40,
        text_style=ft.TextStyle(font_family="RobotoMono", size=tokens.FONT_SM),
        border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_MD),
        on_change=_on_text_change,
        on_selection_change=_on_selection_change,
        hint_text="Write Python here. Use # %% to mark a cell, # %% [markdown] for notes.",
        expand=True,
    )

    return ft.Column(
        controls=[
            editor,
            ft.Row(
                controls=[
                    ft.FilledButton(
                        "Run Cell",
                        icon=ft.Icons.PLAY_ARROW_ROUNDED,
                        on_click=_run_cell,
                        disabled=is_running,
                    ),
                    ft.FilledButton(
                        "Run File",
                        icon=ft.Icons.PLAY_CIRCLE_ROUNDED,
                        on_click=_run_file,
                        disabled=is_running,
                    ),
                    ft.ProgressRing(
                        width=tokens.SPINNER_SM,
                        height=tokens.SPINNER_SM,
                        visible=is_running,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            ),
            output_panel,
        ],
        spacing=tokens.SPACE_SM,
        expand=True,
    )
