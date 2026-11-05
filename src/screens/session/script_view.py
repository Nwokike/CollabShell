"""ScriptView — a Python document, edited as plain text.

A script tab is a FILE, not a view of a cell list. The text in the editor IS
the tab's document: it is stored verbatim and handed to the kernel exactly as
written, so nothing is converted in either direction and no edit can be lost
in a round trip.

The earlier implementation drew a notebook tab as `# %%`-marked text and then
re-split an edit back into cells. That projection is what made the script view
broken in ways the user could feel: an empty cell disappeared on every toggle,
a cell edited back to its earlier text got that cell's stale outputs back, and
`# %%` markers appeared in a document nobody had marked up. One document, one
renderer, no conversion.

Scripts run as files. Notebook cells are available in notebook tabs.
"""

from __future__ import annotations

import logging

import flet as ft

from components.notebook_cell.actions import copy_output
from components.notebook_cell.output import parse_outputs_to_controls
from core import tokens
from core.theme import AppColors
from services.colab.text_files import upload_text_file
from services.script_runner import build_run_file_payload
from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx

logger = logging.getLogger("ScriptView")


@ft.component
def ScriptView(
    session_name: str,
    tab: dict,
    on_script_change=None,
    session_env_override: dict | None = None,
):
    """Render and edit one tab's Python text.

    ``tab`` is the live tab dict (``id``/``name``/``view``/``path``/``script``);
    ``on_script_change(new_text)`` is called on every edit, and the parent owns
    saving it.
    """
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    # Seeded from the tab's document, and re-seeded ONLY when the tab changes —
    # re-seeding on every parent render would overwrite the field mid-keystroke
    # and move the caret.
    text, set_text = ft.use_state(lambda: tab.get("script") or "")
    outputs, set_outputs = ft.use_state([])
    is_running, set_is_running = ft.use_state(False)
    is_saving, set_is_saving = ft.use_state(False)
    seeded_for, set_seeded_for = ft.use_state(tab.get("id"))

    if seeded_for != tab.get("id"):
        set_seeded_for(tab.get("id"))
        set_text(tab.get("script") or "")
        set_outputs([])

    path = str(tab.get("path") or "").strip() or "/content/script.py"

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

    def _run_file(e=None):
        if is_running:
            return
        if not (text or "").strip():
            controller.show_snack("Script is empty.", is_error=True)
            return
        page.run_task(_run, build_run_file_payload(text))

    async def _save_to_session(e=None):
        """Write this document to its path on the session VM.

        The VM only reaches a file through a local upload, so the text is
        staged in a temp file and sent up. An explicit action, on purpose: the
        editor's own storage is local and instant, and a background sync would
        fail silently on a dropped connection.
        """
        if not (text or "").strip():
            controller.show_snack("Script is empty.", is_error=True)
            return
        set_is_saving(True)
        try:
            await upload_text_file(
                services.colab,
                path,
                text,
                session_name=session_name,
                auth_method=state.auth_method,
            )
            controller.show_snack(f"✅ Saved to {path}")
        except Exception as ex:
            logger.warning("Script save failed: %s", ex)
            controller.show_snack(f"❌ Save failed: {ex}", is_error=True)
        finally:
            set_is_saving(False)

    def _on_text_change(e):
        value = e.control.value or ""
        set_text(value)
        if on_script_change:
            on_script_change(value)

    # ── Inline output panel ────────────────────────────────────────────────
    # Rendered through the same parser and the same panel shape the notebook
    # cells use — same terminal background, same dynamic height, same actions
    # — so Run File output looks exactly like notebook output.
    output_controls = parse_outputs_to_controls(outputs)
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

    async def _copy_output_task(e=None):
        await copy_output(page, list(outputs))

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
                        ft.Icons.COPY_ALL_ROUNDED,
                        icon_size=tokens.ICON_SM,
                        tooltip="Copy Output",
                        visible=bool(output_controls),
                        on_click=lambda e: page.run_task(_copy_output_task, e),
                    ),
                    ft.IconButton(
                        ft.Icons.CLEAR_ALL_ROUNDED,
                        icon_size=tokens.ICON_SM,
                        tooltip="Clear Output",
                        on_click=lambda e: set_outputs([]),
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
        visible=bool(outputs) or is_running,
        width=float("inf"),
    )

    editor = ft.TextField(
        value=text,
        multiline=True,
        min_lines=8,
        max_lines=40,
        text_style=ft.TextStyle(font_family="RobotoMono", size=tokens.FONT_SM),
        border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_MD),
        on_change=_on_text_change,
        hint_text="Write Python here. Run File executes the complete script.",
        expand=True,
    )

    return ft.Column(
        controls=[
            ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.CODE_ROUNDED,
                        size=tokens.ICON_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        path,
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        expand=True,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=tokens.SPACE_XS,
                tight=True,
            ),
            editor,
            ft.Row(
                controls=[
                    ft.FilledButton(
                        "Run File",
                        icon=ft.Icons.PLAY_CIRCLE_ROUNDED,
                        on_click=_run_file,
                        disabled=is_running,
                    ),
                    ft.FilledTonalButton(
                        "Save to Colab",
                        icon=ft.Icons.CLOUD_UPLOAD_ROUNDED,
                        on_click=lambda e: page.run_task(_save_to_session, e),
                        disabled=is_running or is_saving,
                    ),
                    ft.ProgressRing(
                        width=tokens.SPINNER_SM,
                        height=tokens.SPINNER_SM,
                        visible=is_running or is_saving,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            ),
            output_panel,
        ],
        spacing=tokens.SPACE_SM,
        expand=True,
    )
