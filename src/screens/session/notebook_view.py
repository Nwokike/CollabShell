"""NotebookView — declarative notebook built on Flet 0.86.x observables.

Cells are `CellData` observables rendered by the `NotebookCell` component.
Streaming output mutates the observable model; Flet's component scheduler
re-renders only the affected cell and coalesces rapid updates automatically.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import flet as ft

from components.env_dialog import show_env_override_dialog
from components.notebook_cell import CellData, NotebookCell
from components.notebook_toolbar import build_notebook_toolbar
from components.shortcuts_help import open_shortcuts_help
from core import tokens
from core.shortcuts import Binding
from core.stdin_hook import show_stdin_dialog
from core.styles import build_banner_ad
from screens.files.modal import show_manage_files_modal
from screens.session.layout import build_action_row
from screens.session.vm_ops import on_auth_gcp, on_mount_drive
from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx

logger = logging.getLogger("colab")

_MAX_OUTPUT_ENTRIES = 5000

# Live per-session bridges, published by NotebookView on every render and read
# by the assistant, which holds no component handle. Cleared on unmount so a
# dead session's tabs are never reachable.
_SESSION_BRIDGES: dict[str, dict] = {}


def _bridges(session_name: str) -> dict | None:
    return _SESSION_BRIDGES.get(session_name)


def write_cells_to_active_tab(
    session_name: str, cells: list[dict], *, origin: str = "assistant"
) -> list | None:
    """Append cells to a session's active notebook tab (assistant bridge).

    Accepts the wire shape [{"type", "source"}] plus an optional
    ``tool_call_id`` per cell; returns the inserted CellData or None when no
    tab is reachable (session not open).

    ``origin`` tags the cells so the UI can tell AI-written cells from the
    user's, and so a chat step row can point back at them.
    """
    from components.notebook_cell import CellData

    bridges = _bridges(session_name)
    if not bridges:
        return None
    insert = bridges.get("insert_cells")
    if insert is None:
        return None
    wire = [
        CellData.from_dict(
            {
                "type": c.get("type", "code"),
                "source": c.get("source", ""),
                "origin": c.get("origin") or origin,
                "tool_call_id": c.get("tool_call_id"),
            }
        )
        for c in (cells or [])
        if isinstance(c, dict)
    ]
    if not wire:
        return None
    return insert(bridges.get("active_tab_id")(), wire)


def reveal_cell(session_name: str, cell_id: str) -> bool:
    """Switch to the tab holding a cell and bring it into view (assistant
    bridge, used by the chat's step→cell tap-through).

    Returns False when the cell cannot be found — it was deleted, or the
    session is not open. Never switches tabs on a miss, so a stale tap cannot
    yank the user somewhere unrelated.
    """
    bridges = _bridges(session_name)
    if not bridges:
        return False
    locate = bridges.get("locate_cell")
    if locate is None:
        return False
    found = locate(cell_id)
    if not found:
        return False
    tab_id, _index = found
    # tab_id is ""/None when the cell sits in the tab already showing, in
    # which case the current view is already right and a switch would only
    # cost a re-render.
    if tab_id and tab_id != bridges.get("active_tab_id")():
        bridges.get("switch_tab")(tab_id)
    focus = bridges.get("focus_cell")
    if focus is not None:
        focus(cell_id)
    return True


def insert_cells_into(
    tab: dict,
    cells: list,
    at_end: bool = True,
    after_id: str | None = None,
) -> list | None:
    """Insert cells into a tab's cell list, returning the new list.

    Pure, so it is testable without a mounted component. ``after_id`` puts the
    cells directly under a named cell — how an in-cell AI answer lands next to
    the question. Falls back to the end when the anchor has gone, so a stale id
    cannot raise.
    """
    if tab is None or not cells:
        return None
    current = list(tab.get("cells") or [])
    if after_id:
        for index, cell in enumerate(current):
            if cell.id == after_id:
                current[index + 1 : index + 1] = cells
                break
        else:
            current.extend(cells)
    elif at_end:
        current.extend(cells)
    else:
        current[0:0] = cells
    return current


def list_tab_summaries(session_name: str) -> str:
    """One line per open tab, for the assistant's list_notebook_tabs tool."""
    bridges = _bridges(session_name)
    if not bridges:
        return None
    tabs = bridges.get("list_tabs")() or []
    if not tabs:
        return "(no tabs)"

    def _describe(t: dict) -> str:
        if t.get("view") == "script":
            # Name the document and its path: "cells" would describe a tab
            # that has none.
            return f"- {t['name']} (Python script at {t.get('path') or '?'})"
        return f"- {t['name']} (notebook, {t.get('cells', 0)} cells)"

    return "\n".join(
        _describe(t) + (" [active]" if t["id"] == bridges.get("active_tab_id")() else "")
        for t in tabs
    )
# Per-cell cap on rendered base64 image bytes (~4 MiB). See enforce_image_budget.
_MAX_IMAGE_BYTES = 4 * 1024 * 1024


def _image_bytes(entry) -> int:
    """Approximate on-the-wire size of one output entry's image payloads."""
    if not isinstance(entry, dict):
        return 0
    data = entry.get("data")
    if not isinstance(data, dict):
        return 0
    return sum(len(v) for v in data.values() if isinstance(v, (str, bytes)))


def enforce_image_budget(cell) -> None:
    """Drop the oldest image-bearing outputs until the cell is in budget.

    Base64 figures are large and the per-tab JSON is rewritten on a 1s
    debounce, so an unbounded plotting loop would write megabytes per second.
    Text output is bounded separately by _MAX_OUTPUT_ENTRIES, so only images
    are evicted here — newest kept, oldest dropped.
    """
    while sum(_image_bytes(e) for e in cell.outputs) > _MAX_IMAGE_BYTES:
        for index, entry in enumerate(cell.outputs):
            if _image_bytes(entry):
                cell.outputs.pop(index)
                break
        else:
            return  # nothing image-bearing left to drop


@ft.component
def NotebookView(
    session_name: str,
    on_switch_terminal,
    register_actions=None,
    on_cells_change=None,
    register_bindings=None,
    session_env_override: dict | None = None,
) -> ft.Control:
    """Notebook tab host: one or more notebooks per session, mirroring the
    terminal panel's TerminalEntry pattern.

    Each tab owns its cells, save timer, and active-cell state. All tabs share
    the session kernel (exec takes session_name); persistence is per-tab
    (notebook_<session>__<tab>.json, legacy single file migrates in).
    """
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    tabs, set_tabs = ft.use_state([])  # noqa: RUF059 (reactive mirror of tabs_ref)
    tabs_ref = ft.use_ref([])
    active_tab_id, set_active_tab_id = ft.use_state(None)
    tab_seq_ref = ft.use_ref([0])
    save_debounce_ref = ft.use_ref(None)
    # ── Active-cell model (keyboard shortcuts, per active tab) ───────────────
    # The active cell is the last one whose editor held focus (sticky — it
    # survives blur, matching Jupyter's selection model). Run/move/delete
    # shortcuts target it. focus_req is (cell_id, counter): bumping the
    # counter asks that cell's editor to grab focus after the next render.
    active_cell_id, set_active_cell_id = ft.use_state("")
    focus_req, set_focus_req = ft.use_state(("", 0))
    focus_sink_ref = ft.use_ref(None)

    def _get_tab(tab_id=None):
        want = tab_id if tab_id is not None else active_tab_id
        for t in tabs_ref.current or []:
            if t["id"] == want:
                return t
        return None

    def _set_tabs(new_list):
        tabs_ref.current = new_list
        set_tabs(list(new_list))
        if on_cells_change:
            total = sum(len(t["cells"]) for t in new_list)
            on_cells_change(total)

    def _publish(tab, new_list):
        tab["cells"] = new_list
        _set_tabs(list(tabs_ref.current or []))

    def _new_tab(name=None, cells=None, tab_id=None, view="notebook"):
        tab_seq_ref.current[0] += 1
        tid = tab_id or f"nb{tab_seq_ref.current[0]}"
        return {
            "id": tid,
            "name": name or f"Notebook {tab_seq_ref.current[0]}",
            "view": view or "notebook",
            "cells": list(cells) if cells else [CellData()],
        }

    def _new_script_tab(name=None, path=None, tab_id=None):
        """A Python file, edited as plain text — not a view of a cell list.

        A script tab used to be a notebook tab rendered as `# %%` text, which
        made every edit a re-split-and-merge against the cell model: empty
        cells were dropped on the way through, and a cell edited back to its
        earlier text got that cell's stale outputs back. One document, one
        renderer: the text is the tab, and `# %%` appears only if the file
        itself uses it.
        """
        tab_seq_ref.current[0] += 1
        tid = tab_id or f"py{tab_seq_ref.current[0]}"
        return {
            "id": tid,
            "name": name or f"Script {tab_seq_ref.current[0]}",
            "view": "script",
            "path": path or f"/content/script_{tab_seq_ref.current[0]}.py",
            "script": "",
            # Kept so every code path that reads `cells` finds a list rather
            # than raising a KeyError on a tab that has none.
            "cells": [],
        }

    def _save_index():
        """Persist tab order/names/view (sidecar to the per-tab documents)."""
        tabs = tabs_ref.current or []
        try:
            page.run_task(
                services.storage.save_tab_index,
                session_name,
                [
                    {
                        "id": t["id"],
                        "name": t.get("name"),
                        "view": t.get("view") or "notebook",
                        "path": t.get("path") or "",
                    }
                    for t in tabs
                ],
            )
        except RuntimeError:
            pass

    async def _load():
        # Restore saved tabs. The index sidecar carries names + order; a glob
        # fallback covers installs whose tabs predate the index.
        index = await services.storage.load_tab_index(session_name)
        saved_ids = await services.storage.list_notebooks(session_name)
        meta_by_id = {
            str(t["id"]): t for t in (index or []) if t.get("id")
        }
        if saved_ids:
            restored = []
            for tid in saved_ids:
                tab_seq_ref.current[0] += 1
                meta = meta_by_id.get(tid, {})
                # A tab's kind comes from the index when it has one. Without an
                # index the document itself says it: a script file exists only
                # for script tabs, so its presence is the kind — one read.
                saved_script = await services.storage.load_script(session_name, tid)
                is_script = meta.get("view") == "script" or (
                    meta.get("view") is None and saved_script is not None
                )
                if is_script:
                    restored.append(
                        {
                            "id": tid,
                            "name": meta.get("name") or tid,
                            "view": "script",
                            "path": meta.get("path") or f"/content/{tid}.py",
                            "script": saved_script or "",
                            "cells": [],
                        }
                    )
                    continue
                cells = await services.storage.load_notebook(session_name, tid)
                cell_list = [CellData.from_dict(c) for c in cells] or [CellData()]
                restored.append(
                    {
                        "id": tid,
                        # A tab the index never named falls back to its id, and
                        # an index is written below so the next launch has a
                        # real name.
                        "name": meta.get("name") or tid,
                        # An old "script view" tab was a notebook rendered as
                        # `# %%` text, not a document of its own. It restores
                        # as the notebook it always was, and its cells survive
                        # — the projection is gone, the work is not.
                        "view": "notebook",
                        "cells": cell_list,
                    }
                )
            _set_tabs(restored)
            set_active_tab_id(restored[0]["id"])
            # Write an index whenever one is missing or names a stale tab set,
            # so legacy/per-tab-only installs migrate in one launch.
            if index is None or {t["id"] for t in restored} != set(meta_by_id):
                _save_index()
        else:
            legacy = await services.storage.load_notebook(session_name)
            cells = [CellData.from_dict(c) for c in legacy] or [CellData()]
            tab = _new_tab(name="Notebook 1", cells=cells, tab_id="nb1")
            _set_tabs([tab])
            set_active_tab_id(tab["id"])
            _save_index()

    async def _finish_pending_reveal():
        """Land on a cell a notification deep-linked to, once it exists.

        A notification tap names the exact tab and cell that finished, but the
        tab's cells only exist after `_load` restores them — so the reveal is
        deferred to here. Taking the pending intent (rather than polling state)
        means a stale tap cannot fire twice.
        """
        pending = getattr(controller, "consume_pending_reveal", None)
        take = None
        if callable(pending):
            take = pending()
        if take is None:
            return
        _encoded, tab_id, cell_id = take
        if tab_id:
            target = _get_tab(tab_id)
            if target is not None and tab_id != active_tab_id:
                _switch_tab(tab_id)
        if cell_id:
            _focus_cell(cell_id)

    async def _finish_pending_fix():
        """A failed cell tapped with "Ask AI to fix": reveal it, then fix it.

        Without this the fix button did exactly what "Open" did — decorative,
        which is worse than not offering it.
        """
        take_fn = getattr(controller, "consume_pending_fix", None)
        take = take_fn() if callable(take_fn) else None
        if take is None:
            return
        _encoded, _tab_id, cell_id = take
        fixed = False
        for cell in _active_cells():
            if cell.id == cell_id:
                await _run_cell_ai("fix", cell_id, "code")
                fixed = True
                break
        if not fixed:
            controller.show_snack("That cell is no longer in the notebook.")

    async def _consume_notification_intents():
        await _finish_pending_reveal()
        await _finish_pending_fix()

    ft.on_mounted(lambda: page.run_task(_consume_notification_intents))
    ft.on_mounted(lambda: page.run_task(_load))

    # ── Persistence (per active tab) ────────────────────────────────────────
    def _save(tab=None):
        target = tab or _get_tab()
        if target is None:
            return
        try:
            if not getattr(page, "_session", getattr(page, "session", None)):
                return
            if (target.get("view") or "notebook") == "script":
                # The script's text is the document: it is stored verbatim,
                # so what comes back on the next launch is exactly what was
                # in the editor.
                page.run_task(
                    services.storage.save_script,
                    session_name,
                    target["id"],
                    target.get("script") or "",
                )
                return
            page.run_task(
                services.storage.save_notebook,
                session_name,
                [c.to_dict() for c in target["cells"] or []],
                target["id"],
            )
        except RuntimeError:
            pass

    def _save_all():
        for t in tabs_ref.current or []:
            _save(t)

    def _debounced_save():
        """Coalesce rapid keystroke saves into one write per second (legacy parity)."""
        if save_debounce_ref.current is not None:
            save_debounce_ref.current.cancel()
        try:
            loop = asyncio.get_running_loop()
            save_debounce_ref.current = loop.call_later(1.0, _save)
        except RuntimeError:
            _save()

    def _flush_pending_save():
        """Save immediately on unmount so the last keystroke is never lost."""
        if save_debounce_ref.current is not None:
            save_debounce_ref.current.cancel()
            save_debounce_ref.current = None
        _save_all()
        # The session's tabs are gone; drop the bridge so the assistant cannot
        # write into a closed session.
        _SESSION_BRIDGES.pop(session_name, None)

    ft.on_unmounted(_flush_pending_save)

    # ── Output streaming ──────────────────────────────────────────────���────────
    def _append_output(cell: CellData, text_or_dict):
        entry = (
            text_or_dict
            if isinstance(text_or_dict, dict)
            else {"type": "stream", "text": str(text_or_dict)}
        )
        if len(cell.outputs) >= _MAX_OUTPUT_ENTRIES:
            cell.outputs.pop(0)
        cell.outputs.append(entry)
        enforce_image_budget(cell)
        cell.outputs_rev += 1

    # ── Cell execution ────────────────────────────────────────────────────────
    # Per-session env override: memory-only, cleared when the session screen
    # unmounts. The dict is owned by the session screen (shared with the
    # header env icon); this view holds a reference, never a copy.
    # Effective env = state.default_env merged with this (override wins).
    if session_env_override is None:
        session_env_override = {}

    def _effective_env() -> dict:
        merged = dict(getattr(state, "default_env", {}) or {})
        merged.update(session_env_override)
        return merged

    async def _run_cell(cell: CellData):
        if cell.is_running:
            return
        cell.is_running = True
        cell.outputs.clear()
        cell.outputs_rev += 1
        # Elapsed time decides whether a finished cell is worth an OS
        # notification at all — a two-second cell must not ping anyone.
        started = time.monotonic()

        def _on_output(text_or_dict):
            page.loop.call_soon_threadsafe(_append_output, cell, text_or_dict)

        def _stdin_hook(prompt, *args, **kwargs):
            return show_stdin_dialog(
                page, prompt, controller.show_snack, *args, **kwargs
            )

        ok = True
        try:
            await services.colab.exec_code(
                cell.source,
                session_name,
                timeout=float(state.default_timeout),
                auth_method=state.auth_method,
                on_output=_on_output,
                intercept_oauth=True,
                stdin_hook=_stdin_hook,
                env=_effective_env() or None,
            )
        except Exception as ex:
            ok = False
            _append_output(cell, {"type": "error", "traceback": [str(ex)]})
        finally:
            cell.is_running = False
            _save()
            # Tell the OS. A cell can train for twenty minutes; without this the
            # only way to learn it finished is to come back and look.
            await _notify_cell_done(cell, ok, time.monotonic() - started)

    async def _notify_cell_done(cell: CellData, ok: bool, duration_sec: float = 0.0):
        """Post the OS notification for a finished cell. Never raises."""
        notify = getattr(services, "notify", None)
        if notify is None:
            return
        tab = _get_tab()
        try:
            await notify.cell_done(
                session_name=session_name,
                tab_id=tab["id"] if tab else "",
                cell_id=cell.id,
                ok=ok,
                duration_sec=duration_sec,
                detail=_first_error_line(cell) if not ok else _output_digest(cell),
            )
        except Exception as ex:
            logger.debug("cell notify failed: %s", ex)

    def _first_error_line(cell) -> str:
        for entry in getattr(cell, "outputs", None) or []:
            if isinstance(entry, dict) and entry.get("type") == "error":
                traceback = entry.get("traceback") or []
                return str(traceback[-1] if traceback else entry)[:180]
        return ""

    def _output_digest(cell) -> str:
        """A short, honest digest of what the cell produced."""
        for entry in reversed(list(getattr(cell, "outputs", None) or [])):
            if isinstance(entry, dict):
                text = entry.get("text") or entry.get("output")
                if text:
                    return " ".join(str(text).split())[:180]
        return ""

    def _stop_cell(cell: CellData):
        services.colab.cancel()
        _append_output(
            cell, {"type": "error", "traceback": ["Execution cancelled by user"]}
        )
        cell.is_running = False
        _save()

    # ── Cell list operations (active tab) ───────────────────────────────────
    def _active_cells() -> list:
        tab = _get_tab()
        return tab["cells"] if tab else []

    # ── In-cell AI (M5): Explain / Fix error / Suggest next ─────────────────
    # The three actions live here rather than in the cell component so the
    # service calls, metering and insertion all sit next to the tab machinery
    # they need. They are always offered: the assistant is part of the app, not
    # a mode to switch on.

    def _insert_ai_answer(cell_id: str, text: str, kind: str) -> bool:
        """Put an answer under `cell_id` as a new cell, focused and editable.

        Markdown for prose (Explain), code for code (Fix, Suggest). Returns
        False when there was nothing to insert — the caller turns that into a
        notice rather than leaving an empty cell behind.
        """
        from components.notebook_cell import CellData

        body = text.strip()
        if not body:
            return False
        tab = _get_tab()
        if tab is None:
            return False
        if kind == "code":
            from services.cell_ai import extract_code

            body = extract_code(body)
            if not body:
                return False
        cell = CellData(cell_type=kind, source=body, origin="assistant")
        inserted = _insert_cells(tab["id"], [cell], after_id=cell_id)
        if not inserted:
            return False
        # Start code answers in edit mode so they are immediately editable, and
        # pull focus so the user lands in it rather than hunting for it.
        cell.is_editing = kind == "code"
        _focus_cell(cell.id)
        return True

    async def _run_cell_ai(action: str, cell_id: str, kind: str):
        """Run one in-cell action against a cell and file the answer under it.

        Every failure path is a notice, never a raised exception: this runs
        from a button press, and an unhandled error there would take the cell
        UI down with it.
        """
        from services import cell_ai

        cell = next((c for c in _active_cells() if c.id == cell_id), None)
        if cell is None:
            return
        credits = getattr(services, "credits", None)
        try:
            text = await cell_ai.run_cell_action(
                action=action,
                state=state,
                credits=credits,
                services=services,
                source=cell.source,
                notebook_cells=_active_cells(),
                output=_output_text(cell),
                cell=cell,
            )
        except cell_ai.OutOfCredits:
            _ai_notice("Out of assistant credits — top up in Assistant settings.")
            return
        except cell_ai.CellAIDisabled:
            _ai_notice("Assistant credits are unavailable in this build.")
            return
        except Exception as ex:
            logger.warning("In-cell AI %s failed: %s", action, ex)
            _ai_notice("The Assistant could not answer just now.")
            return

        if not _insert_ai_answer(cell_id, text, kind):
            _ai_notice("The Assistant returned nothing usable.")

    async def _suggest_hardware():
        """Ask what runtime shape this notebook wants (4C).

        Notebook-scoped, so there is no anchor cell — the answer is appended
        at the end as a markdown cell, which is where a recommendation reads
        best anyway.
        """
        from services import cell_ai

        tab = _get_tab()
        if tab is None:
            return
        try:
            text = await cell_ai.run_cell_action(
                action="hardware",
                state=state,
                credits=getattr(services, "credits", None),
                services=services,
                source="",
                notebook_cells=_active_cells(),
            )
        except cell_ai.OutOfCredits:
            _ai_notice("Out of assistant credits — top up in Assistant settings.")
            return
        except cell_ai.CellAIDisabled:
            _ai_notice("Assistant credits are unavailable in this build.")
            return
        except Exception as ex:
            logger.warning("Hardware suggestion failed: %s", ex)
            _ai_notice("The Assistant could not answer just now.")
            return

        if not tab["cells"] or not text.strip():
            _ai_notice("The Assistant returned nothing usable.")
            return
        from components.notebook_cell import CellData

        cell = CellData(cell_type="markdown", source=text.strip(), origin="assistant")
        _insert_cells(tab["id"], [cell])
        _focus_cell(cell.id)

    def _ai_notice(message: str):
        from core.notifications import show_notification

        try:
            show_notification(page, message, is_warning=True)
        except Exception:
            logger.debug("cell AI notice failed")

    def _output_text(cell) -> str:
        from services.cell_ai import _output_digest

        return _output_digest(cell)

    def _show_cell_ai_menu(cell_id: str):
        """The Ask-AI menu: Explain / Fix error / Suggest next."""
        from components.notebook_cell.actions import ai_menu

        ai_menu(page, cell_id, on_pick=lambda action, cid=cell_id: page.run_task(
            _run_cell_ai, action, cid, "markdown" if action == "explain" else "code"
        ))

    # ── Cell list operations (active tab) ───────────────────────────────────
    def _active_cells() -> list:
        tab = _get_tab()
        return tab["cells"] if tab else []

    def _add_cell(cell_type: str):
        tab = _get_tab()
        if tab is None:
            return
        c_list = list(tab["cells"] or [])
        c_list.append(CellData(cell_type=cell_type))
        _publish(tab, c_list)
        _save(tab)

    def _delete_cell(cell: CellData):
        tab = _get_tab()
        if tab is None:
            return
        c_list = [c for c in tab["cells"] or [] if c.id != cell.id]
        _publish(tab, c_list)
        _save(tab)

    def _move_cell(cell: CellData, direction: int):
        tab = _get_tab()
        if tab is None:
            return
        c_list = list(tab["cells"] or [])
        idx = next((i for i, c in enumerate(c_list) if c.id == cell.id), -1)
        new_idx = idx + direction
        if idx < 0 or not 0 <= new_idx < len(c_list):
            return
        c_list[idx], c_list[new_idx] = c_list[new_idx], c_list[idx]
        _publish(tab, c_list)
        _save(tab)

    def _clear_cell_output(cell: CellData):
        cell.outputs.clear()
        cell.outputs_rev += 1
        _save()

    # ── Active-cell operations (keyboard shortcuts) ──────────────────────────
    def _active_cell() -> CellData | None:
        c_list = _active_cells()
        for c in c_list:
            if c.id == active_cell_id:
                return c
        return c_list[-1] if c_list else None

    def _focus_cell(cell_id: str):
        set_focus_req((cell_id, (focus_req[1] or 0) + 1))

    def _locate_cell(cell_id: str) -> tuple[str, int] | None:
        """Find which tab holds a cell and where, or None if it is gone.

        The cell may have been deleted or moved since the assistant wrote it,
        so the caller must treat None as "nothing to reveal" rather than an
        error.
        """
        for tab in tabs_ref.current or []:
            for index, cell in enumerate(tab.get("cells") or []):
                if cell.id == cell_id:
                    return (tab["id"], index)
        return None

    def _on_cell_focus(cell_id: str, focused: bool):
        if focused and cell_id != active_cell_id:
            set_active_cell_id(cell_id)

    def _insert_cell_near(above: bool, after_id: str | None = None):
        """Insert a code cell above/below the active cell (or at the end)."""
        tab = _get_tab()
        if tab is None:
            return
        c_list = list(tab["cells"] or [])
        anchor_id = after_id or active_cell_id
        anchor_idx = next((i for i, c in enumerate(c_list) if c.id == anchor_id), -1)
        new_cell = CellData(cell_type="code")
        if anchor_idx == -1:
            c_list.append(new_cell)
        else:
            c_list.insert(anchor_idx if above else anchor_idx + 1, new_cell)
        _publish(tab, c_list)
        _save(tab)
        set_active_cell_id(new_cell.id)
        _focus_cell(new_cell.id)

    def _delete_active():
        cell = _active_cell()
        if cell:
            _delete_cell(cell)

    def _move_active(direction: int):
        cell = _active_cell()
        if cell:
            _move_cell(cell, direction)

    def _toggle_active_type():
        cell = _active_cell()
        if not cell:
            return
        if cell.type == "code":
            cell.type = "markdown"
            cell.is_editing = True  # edit immediately after switching
        else:
            cell.type = "code"
            cell.is_editing = False
        _save()
        _focus_cell(cell.id)

    async def _run_all():
        for cell in list(_active_cells()):
            if cell.type == "code" and (cell.source or "").strip():
                await _run_cell(cell)

    def _shortcut_run(advance: str):
        """Run the active cell; advance = "next" | "insert" | "inplace"."""
        cell = _active_cell()
        if cell is None:
            return
        page.run_task(_run_cell, cell)
        if advance == "inplace":
            return
        c_list = list(_active_cells())
        idx = next((i for i, c in enumerate(c_list) if c.id == cell.id), -1)
        if advance == "insert" or idx == len(c_list) - 1:
            _insert_cell_near(above=False, after_id=cell.id)
        elif idx >= 0:
            _focus_cell(c_list[idx + 1].id)

    def _blur_editor():
        """Escape: pull focus out of the editor so markdown renders on blur.

        TextField has no blur() in Flet 0.86, so focus travels to an
        invisible focusable sink instead.
        """
        sink = focus_sink_ref.current
        if sink is not None:
            try:
                page.run_task(sink.focus)
            except RuntimeError:
                logger.debug("Focus sink not ready", exc_info=True)

    def _clear_all_outputs(e=None):
        for cell in _active_cells():
            cell.outputs.clear()
            cell.outputs_rev += 1
        _save()

    # ── Notebook tabs (multiple notebooks, one shared kernel) ────────────────
    def _switch_tab(tab_id: str):
        target = _get_tab(tab_id)
        if target is None:
            return
        _save()  # flush the outgoing tab before switching
        set_active_tab_id(tab_id)
        first = (target["cells"] or [None])[0]
        if first is not None:
            set_active_cell_id(first.id)

    def _create_tab(e=None):
        tab = _new_tab()
        tabs = list(tabs_ref.current or [])
        tabs.append(tab)
        _set_tabs(tabs)
        _save(tab)
        _save_index()
        set_active_tab_id(tab["id"])
        set_active_cell_id((tab["cells"][0]).id)

    def _create_script_tab(name=None, path=None):
        """Open a new Python script tab and make it the active tab."""
        tab = _new_script_tab(name=name, path=path)
        tabs = list(tabs_ref.current or [])
        tabs.append(tab)
        _set_tabs(tabs)
        _save(tab)
        _save_index()
        set_active_tab_id(tab["id"])
        set_active_cell_id("")

    def _show_new_script_dialog(e=None):
        """Ask for the script's name and path before creating the tab.

        Both fields are real: the name labels the tab, and the path is where
        the file lives on the session VM and where "Save to session" writes.
        """
        name_ref = ft.Ref[ft.TextField]()
        path_ref = ft.Ref[ft.TextField]()
        next_id = f"py{tab_seq_ref.current[0] + 1}"

        def _commit(ev=None):
            name = (name_ref.current.value if name_ref.current else "") or ""
            path = (path_ref.current.value if path_ref.current else "") or ""
            page.pop_dialog()
            _create_script_tab(
                name=name.strip() or None,
                path=path.strip() or f"/content/{next_id}.py",
            )

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("New Python script"),
                content=ft.Column(
                    controls=[
                        ft.TextField(
                            ref=name_ref,
                            label="Tab name",
                            hint_text="Pipeline",
                            autofocus=True,
                            on_submit=lambda ev: _commit(),
                        ),
                        ft.TextField(
                            ref=path_ref,
                            label="Path on the session",
                            hint_text=f"/content/{next_id}.py",
                            prefix_text="/content/",
                            on_submit=lambda ev: _commit(),
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                    tight=True,
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda ev: page.pop_dialog()),
                    ft.FilledButton("Create", on_click=lambda ev: _commit()),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    async def _export_script(e=None):
        """Save the active script's text to a local file."""
        import os

        tab = _get_tab()
        if tab is None:
            return
        filename = f"{session_name}_{tab['name'].replace(' ', '_')}.py"
        if page.platform.is_mobile():
            dl_dir = "/storage/emulated/0/Download"
            if not os.path.exists(dl_dir):
                dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(dl_dir, exist_ok=True)
            path = os.path.join(dl_dir, filename)
        else:
            try:
                path = await page.file_picker.save_file(
                    allowed_extensions=["py"], file_name=filename
                )
            except ValueError:
                dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                os.makedirs(dl_dir, exist_ok=True)
                path = os.path.join(dl_dir, filename)
        if path:
            try:
                Path(path).write_text(tab.get("script") or "", encoding="utf-8")
                controller.show_snack(f"✅ Saved {filename}")
            except Exception as ex:
                logger.exception("Script export failed")
                controller.show_snack(f"❌ Export failed: {ex}", is_error=True)

    async def _import_script(e=None):
        """Load a local Python file into the active script tab, text as-is."""
        tab = _get_tab()
        if tab is None:
            return
        try:
            files = await page.file_picker.pick_files(
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["py"],
                allow_multiple=False,
            )
            if not files or not files[0].path:
                return
            raw = Path(files[0].path).read_text(encoding="utf-8")
            _on_script_change(raw)
            controller.show_snack(f"✅ Loaded {files[0].name}")
        except Exception as ex:
            logger.exception("Script import failed")
            controller.show_snack(f"❌ Import failed: {ex}", is_error=True)

    def _close_tab(tab_id: str):
        tabs = [t for t in tabs_ref.current or [] if t["id"] != tab_id]
        closing = _get_tab(tab_id)
        if closing is not None:
            _save(closing)
            # Delete the document that tab actually owns: a script tab has no
            # cell file, and deleting the wrong one leaves an orphan behind.
            if (closing.get("view") or "notebook") == "script":
                page.run_task(
                    services.storage.delete_script, session_name, closing["id"]
                )
            else:
                page.run_task(
                    services.storage.delete_notebook, session_name, closing["id"]
                )
        if not tabs:
            tabs = [_new_tab(name="Notebook 1", tab_id="nb1")]
            _save(tabs[0])
        _set_tabs(tabs)
        _save_index()
        if active_tab_id == tab_id or _get_tab() is None:
            set_active_tab_id(tabs[-1]["id"])

    def _rename_tab(tab_id: str, new_name: str):
        """Rename a tab, persisting it through the index sidecar."""
        new_name = (new_name or "").strip()
        target = _get_tab(tab_id)
        if target is None or not new_name:
            return
        target["name"] = new_name
        _set_tabs(list(tabs_ref.current or []))
        _save(target)
        _save_index()

    def _show_rename_dialog(tab_id: str):
        target = _get_tab(tab_id)
        if target is None:
            return
        field_ref = ft.Ref[ft.TextField]()

        def _commit(ev=None):
            page.pop_dialog()
            _rename_tab(tab_id, field_ref.current.value if field_ref.current else "")

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Rename notebook"),
                content=ft.TextField(
                    ref=field_ref,
                    value=target["name"],
                    autofocus=True,
                    on_submit=lambda ev: _commit(),
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda ev: page.pop_dialog()),
                    ft.FilledButton("Rename", on_click=lambda ev: _commit()),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    def _insert_cells(
        tab_id: str,
        cells: list[CellData],
        at_end: bool = True,
        after_id: str | None = None,
    ):
        """Insert cells into a named tab without switching to it.

        Stable entry point for the Assistant bridge (Phase 4): the AI targets
        a tab directly instead of synthesising taps. Selecting the tab would
        steal focus from the chat, so the target tab keeps its active state.

        A script tab is a Python document, not a cell list, so it refuses:
        writing cells into one would be the projection that used to make the
        script view lose work. The caller reports it as "no notebook tab".
        """
        target = _get_tab(tab_id)
        if target is None or not cells:
            return None
        if (target.get("view") or "notebook") == "script":
            return None
        merged = insert_cells_into(target, cells, at_end, after_id)
        if merged is None:
            return None
        _publish(target, merged)
        _save(target)
        return cells

    # ── Export / import (active tab) ─────────────────────────────────────────
    async def _write_export(path: str, fmt: str, c_list: list[dict]):
        """Serialize the active tab to *path* in the chosen format."""
        try:
            if fmt == "py":
                from services.ipynb_converter import cells_to_py

                body = cells_to_py(c_list)
            else:
                from services.ipynb_converter import cells_to_ipynb

                body = json.dumps(
                    cells_to_ipynb(c_list), ensure_ascii=False, indent=2
                )
            Path(path).write_text(body, encoding="utf-8")
            controller.show_snack(f"✅ Exported as {fmt}")
        except Exception as ex:
            logger.exception("Export failed")
            controller.show_snack(f"❌ Export failed: {ex}", is_error=True)

    async def _export_as(fmt: str):
        tab = _get_tab()
        tab_name = (tab["name"] if tab else "notebook").replace(" ", "_")
        ext = "py" if fmt == "py" else "ipynb"
        filename = f"{session_name}_{tab_name}.{ext}"
        c_list = [c.to_dict() for c in _active_cells()]
        if page.platform.is_mobile():
            dl_dir = "/storage/emulated/0/Download"
            if not os.path.exists(dl_dir):
                dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(dl_dir, exist_ok=True)
            path = os.path.join(dl_dir, filename)
        else:
            try:
                path = await page.file_picker.save_file(
                    allowed_extensions=[ext],
                    file_name=filename,
                )
            except ValueError:
                dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                os.makedirs(dl_dir, exist_ok=True)
                path = os.path.join(dl_dir, filename)
        if path:
            await _write_export(path, fmt, c_list)

    def _show_export_dialog(e=None):
        """Choose the export format before saving.

        The two options are genuinely different documents, so the copy says
        what each one keeps and drops rather than leaving the user to guess.

        A script tab has no formats to choose between — it is already Python —
        so it exports its text straight away rather than offering a choice that
        would describe a cell list it does not have.
        """
        if (_get_tab() or {}).get("view") == "script":
            page.run_task(_export_script)
            return

        def _pick(fmt):
            page.pop_dialog()
            page.run_task(_export_as, fmt)

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Export notebook"),
                content=ft.Column(
                    controls=[
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.DESCRIPTION_OUTLINED),
                            title=ft.Text("Jupyter notebook (.ipynb)"),
                            subtitle=ft.Text(
                                "Cells, markdown, and outputs — opens in "
                                "Colab or Jupyter."
                            ),
                            on_click=lambda ev: _pick("ipynb"),
                        ),
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.CODE_ROUNDED),
                            title=ft.Text("Python script (.py)"),
                            subtitle=ft.Text(
                                "Code only, split into # %% cells — opens in "
                                "any editor or IDE."
                            ),
                            on_click=lambda ev: _pick("py"),
                        ),
                    ],
                    spacing=tokens.SPACE_XS,
                    tight=True,
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda ev: page.pop_dialog()),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    async def _import_ipynb(e=None):
        """Import a `.ipynb` notebook, or a `.py` script (becomes code cells).

        Imports target the ACTIVE tab (no longer clobbers blindly — the file
        lands in the current tab, other tabs untouched). A script tab loads the
        file's text instead of splitting it into cells it cannot show.
        """
        from services.ipynb_converter import ipynb_to_cells, py_to_cells

        tab = _get_tab()
        if tab is None:
            return
        if (tab.get("view") or "notebook") == "script":
            await _import_script(e)
            return
        try:
            files = await page.file_picker.pick_files(
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["ipynb", "py"],
                allow_multiple=False,
            )
            if files:
                fpath = files[0].path
                if fpath:
                    raw = Path(fpath).read_text(encoding="utf-8")
                    if files[0].name.lower().endswith(".py"):
                        imported = py_to_cells(raw)
                    else:
                        imported = ipynb_to_cells(json.loads(raw))
                    _publish(tab, [CellData.from_dict(c) for c in imported])
                    _save(tab)
                    controller.show_snack(
                        f"✅ Imported {len(imported)} cell{'s' if len(imported) != 1 else ''} from {files[0].name}"
                    )
        except Exception as ex:
            logger.exception("Import notebook failed")
            controller.show_snack(f"❌ Import failed: {ex}", is_error=True)

    # Expose notebook actions to the SessionScreen FAB overflow menu.
    if register_actions:
        register_actions(
            {
                "export_ipynb": lambda: _show_export_dialog(),
                "import_ipynb": lambda: page.run_task(_import_ipynb),
                "clear_all": _clear_all_outputs,
                "new_notebook": lambda: _create_tab(),
                "new_script": lambda: _show_new_script_dialog(),
                "rename_notebook": lambda: _show_rename_dialog(active_tab_id)
                if active_tab_id
                else None,
                "close_notebook": lambda: _close_tab(active_tab_id)
                if active_tab_id
                else None,
                "switch_notebook": lambda tid: _switch_tab(tid),
                "insert_cells": _insert_cells,
                # The FAB's "Ask AI about this cell" and Ctrl+I both target
                # the active cell, so there is one path to build.
                "ask_ai_active": (
                    lambda: _show_cell_ai_menu(active_cell_id)
                    if active_cell_id
                    else None
                ),
                # Notebook-scoped: "what runtime shape should I use for this?"
                "suggest_hardware": lambda: page.run_task(_suggest_hardware),
            }
        )

    # Publish the live per-session bridges so the assistant (which holds no
    # component handle) can reach this session's tabs. Replaced on every
    # render so a rebuilt view is never stale.
    _SESSION_BRIDGES[session_name] = {
        "insert_cells": _insert_cells,
        "list_tabs": lambda: [
            {
                "id": t["id"],
                "name": t.get("name") or t["id"],
                "view": t.get("view") or "notebook",
                "path": t.get("path") or "",
                "cells": len(t.get("cells") or []),
            }
            for t in (tabs_ref.current or [])
        ],
        "read_cells": lambda tab_id=None: [
            c.to_dict() for c in (_get_tab(tab_id)["cells"] or [])
        ]
        if _get_tab(tab_id) is not None
        else [],
        # The active tab itself, so a caller can tell a Python script tab from
        # a notebook before asking it for cells it does not have.
        "active_tab": lambda: _get_tab(),
        "switch_tab": _switch_tab,
        "active_tab_id": lambda: active_tab_id,
        # Bring a cell into view and put the caret in it. Bumps the shared
        # focus request, so the cell's editor focuses and the scrollable
        # brings it into view — the same path the keyboard shortcuts use,
        # which is why no separate scroll machinery was needed.
        "focus_cell": _focus_cell,
        # Where a cell lives: (tab_id, index) or None. Used by the chat's
        # step→cell tap-through to switch to the right tab first.
        "locate_cell": _locate_cell,
    }

    # Refresh the shortcut binding table every render so the router always
    # sees current closures (cells, handlers). Writing to the session's ref
    # is side-effect free — no re-render loop.
    if register_bindings:
        register_bindings(
            [
                (
                    Binding("Enter", ctrl=True, shift=True),
                    lambda: page.run_task(_run_all),
                ),
                (Binding("Enter", shift=True), lambda: _shortcut_run("next")),
                (Binding("Enter", alt=True), lambda: _shortcut_run("insert")),
                (Binding("Enter", ctrl=True), lambda: _shortcut_run("inplace")),
                (Binding("s", ctrl=True), lambda: _show_export_dialog()),
                (Binding("a", ctrl=True, shift=True), lambda: _insert_cell_near(True)),
                (Binding("b", ctrl=True, shift=True), lambda: _insert_cell_near(False)),
                (Binding("ArrowUp", alt=True), lambda: _move_active(-1)),
                (Binding("ArrowDown", alt=True), lambda: _move_active(1)),
                (Binding("d", ctrl=True, shift=True), _delete_active),
                (Binding("m", ctrl=True, shift=True), _toggle_active_type),
                # Ctrl+I opens the in-cell AI menu on the active cell. Same
                # picker as the sparkle button, so there is one thing to learn.
                (
                    Binding("i", ctrl=True),
                    (
                        lambda: _show_cell_ai_menu(active_cell_id)
                        if active_cell_id
                        else None
                    ),
                ),
                (Binding("Escape"), _blur_editor),
                (Binding("F1"), lambda: open_shortcuts_help(page, "notebook")),
            ]
        )

    # ── Action row ──────────────────────────────────────────────────────────

    # ── Restart / Stop confirm dialogs ────────────────────────────────────────
    async def _do_restart():
        controller.show_snack("Restarting kernel...")
        try:
            await services.colab.restart_kernel(
                session_name, auth_method=state.auth_method
            )
            controller.show_snack("✅ Kernel restarted")
        except Exception as ex:
            controller.show_snack(f"❌ {ex}", is_error=True)

    def _on_restart(e=None):
        def _close(ev=None):
            page.pop_dialog()

        def _confirm(ev):
            page.pop_dialog()
            page.run_task(_do_restart)

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Restart Kernel?"),
                content=ft.Text(
                    "This will restart the Python kernel. All variables will be lost."
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=_close),
                    ft.FilledButton("Restart", on_click=_confirm),
                ],
            )
        )

    async def _do_stop():
        controller.show_snack("Stopping session...")
        try:
            await services.colab.stop_session(
                session_name, auth_method=state.auth_method
            )
            controller.show_snack("✅ Session terminated")
            try:
                state.active_sessions = (
                    await services.colab.list_sessions(auth_method=state.auth_method)
                    or []
                )
            except Exception:
                logger.exception("Suppressed exception")
            controller.close_session()
        except Exception as ex:
            controller.show_snack(f"❌ {ex}", is_error=True)

    def _on_stop(e=None):
        def _close(ev=None):
            page.pop_dialog()

        def _confirm(ev):
            page.pop_dialog()
            page.run_task(_do_stop)

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Stop Session?"),
                content=ft.Text(
                    "This will terminate the session and release all resources."
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=_close),
                    ft.FilledButton("Stop", on_click=_confirm),
                ],
            )
        )

    action_row = build_action_row(
        page,
        on_files=lambda e: show_manage_files_modal(
            page,
            services.colab,
            session_name,
            auth_method=state.auth_method,
            ad_service=services.ad_service,
            state=state,
        ),
        on_mount_drive=lambda e: page.run_task(
            on_mount_drive,
            page=page,
            session_name=session_name,
            colab_service=services.colab,
            state=state,
            snack=controller.show_snack,
        ),
        on_auth_gcp=lambda e: page.run_task(
            on_auth_gcp,
            page=page,
            session_name=session_name,
            colab_service=services.colab,
            state=state,
            snack=controller.show_snack,
        ),
        on_open_browser=lambda e: page.run_task(
            ft.UrlLauncher().launch_url,
            f"https://colab.research.google.com/drive/{session_name}",
        ),
        on_terminal=lambda e: on_switch_terminal(),
        on_view_logs=lambda e: controller.open_history(session_name),
        on_restart=_on_restart,
        on_stop=_on_stop,
        on_env=lambda e: show_env_override_dialog(
            page, state, session_env_override, on_save=lambda _env: None
        ),
    )

    # Import/Export are shared by both document types; what they move depends
    # on the tab's kind, so the trailing handlers are chosen per view.
    _trailing = {
        "on_export_ipynb": lambda e: _show_export_dialog(),
        "on_import_ipynb": lambda e: page.run_task(_import_ipynb, e),
    }

    # ── Render cells (active tab only) ──────────────────────────────────────
    active_tab = _get_tab()

    if (active_tab or {}).get("view") == "script":
        # A Python document has no cells to add and no outputs to clear, and
        # its import/export is the file's own text rather than a cell list.
        toolbar = build_notebook_toolbar(
            on_add_code=None,
            on_add_markdown=None,
            on_clear_all=None,
            on_export_ipynb=lambda e: page.run_task(_export_script),
            on_import_ipynb=lambda e: page.run_task(_import_script),
        )
    else:
        toolbar = build_notebook_toolbar(
            on_add_code=lambda e: _add_cell("code"),
            on_add_markdown=lambda e: _add_cell("markdown"),
            **_trailing,
        )
    active_cells = active_tab["cells"] if active_tab else []
    cell_controls = []
    for i, cell in enumerate(active_cells):
        cell_controls.append(
            NotebookCell(
                cell,
                key=ft.ValueKey(f"cell_{cell.id}"),
                on_run=lambda c=cell: page.run_task(_run_cell, c),
                on_stop=lambda c=cell: _stop_cell(c),
                on_delete=lambda c=cell: _delete_cell(c),
                on_move_up=lambda c=cell: _move_cell(c, -1),
                on_move_down=lambda c=cell: _move_cell(c, 1),
                on_source_change=lambda value: _debounced_save(),
                on_clear_output=lambda c=cell: _clear_cell_output(c),
                on_open_terminal=on_switch_terminal,
                is_active=cell.id == active_cell_id,
                on_focus_change=_on_cell_focus,
                focus_token=(focus_req[1] if focus_req[0] == cell.id else 0),
                # Always offered: the assistant is part of the app. A button
                # that only works after flipping a switch is worse than none.
                on_ask_ai=lambda c=cell: _show_cell_ai_menu(c.id),
            )
        )
        if (i + 1) % 2 == 0:
            cell_controls.append(build_banner_ad(page))

    # ── Notebook tab bar (mirrors the terminal panel's tab pattern) ─────────
    def _tab_button(tab):
        is_active = tab["id"] == active_tab_id
        # A script tab says so with its own icon, so the document type is
        # readable at a glance instead of only after clicking into it.
        tab_icon = (
            ft.Icons.CODE_ROUNDED
            if (tab.get("view") or "notebook") == "script"
            else ft.Icons.DESCRIPTION_OUTLINED
        )
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        tab_icon,
                        size=tokens.ICON_SM,
                        color=ft.Colors.PRIMARY
                        if is_active
                        else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        tab["name"],
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_600 if is_active else None,
                        color=ft.Colors.PRIMARY
                        if is_active
                        else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.GestureDetector(
                        content=ft.Icon(
                            ft.Icons.CLOSE_ROUNDED,
                            size=tokens.ICON_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        on_tap=lambda e, tid=tab["id"]: _close_tab(tid),
                    ),
                ],
                spacing=tokens.SPACE_XS,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(
                tokens.SPACE_SM, tokens.SPACE_XS, tokens.SPACE_SM, tokens.SPACE_XS
            ),
            border_radius=tokens.RADIUS_MD,
            bgcolor=ft.Colors.with_opacity(
                0.12 if is_active else 0.04, ft.Colors.PRIMARY
            ),
            tooltip="Tap to switch · long-press to rename",
            on_click=lambda e, tid=tab["id"]: _switch_tab(tid),
            # Long-press reveals the rename dialog — the discoverable path is
            # the FAB's "Rename Notebook" entry.
            on_long_press=lambda e, tid=tab["id"]: _show_rename_dialog(tid),
            ink=True,
        )

    # Per-tab view toggle: same document, second renderer. Persisted through
    # the index so a tab reopens the way it was left.
    tab_bar = ft.Row(
        controls=[
            *[_tab_button(t) for t in tabs_ref.current or []],
            ft.IconButton(
                icon=ft.Icons.ADD_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="New notebook",
                on_click=lambda e: _create_tab(),
            ),
            ft.IconButton(
                icon=ft.Icons.INSERT_DRIVE_FILE_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="New Python script",
                on_click=lambda e: _show_new_script_dialog(),
            ),
        ],
        spacing=tokens.SPACE_XS,
        scroll=ft.ScrollMode.AUTO,
    )

    def _on_script_change(new_text: str):
        """Keep the active script tab's text current, saving on a debounce.

        The text IS the tab, so the in-memory copy is updated on every
        keystroke and only the storage write is coalesced — an export a moment
        after typing must not read a stale document. The old implementation
        re-split the text into cells and merged them back, which is what
        dropped empty cells and handed a reverted edit its stale outputs.
        """
        target = _get_tab()
        if target is None:
            return
        target["script"] = new_text or ""
        _set_tabs(list(tabs_ref.current or []))
        _debounced_save()

    # Invisible focusable sink — Escape moves focus here so editors blur and
    # markdown cells render (kept 1px, not 0, so the focus node stays live).
    focus_sink = ft.KeyboardListener(
        content=ft.Container(
            width=1, height=1, content=ft.Container(width=0, height=0)
        ),
        ref=focus_sink_ref,
    )

    def _document_container() -> ft.Container:
        """Cell boxes or the script editor — one renderer per document type."""
        if (active_tab or {}).get("view") == "script":
            from screens.session.script_view import ScriptView

            return ft.Container(
                key=ft.ValueKey(f"script_{(active_tab or {}).get('id', 'none')}"),
                content=ScriptView(
                    session_name=session_name,
                    tab=active_tab,
                    on_script_change=_on_script_change,
                    session_env_override=session_env_override,
                ),
                padding=ft.Padding(tokens.SPACE_MD, 0, tokens.SPACE_MD, tokens.SPACE_XL),
                expand=True,
            )
        return ft.Container(
            # Keyed per tab so editors keep state across tab switches
            # (terminal panel host_{id} pattern).
            key=ft.ValueKey(f"notebook_{(active_tab or {}).get('id', 'none')}"),
            content=ft.Column(controls=cell_controls, spacing=0),
            padding=ft.Padding(
                tokens.SPACE_MD, 0, tokens.SPACE_MD, tokens.SPACE_XL
            ),
        )

    notebook_body = ft.Column(
        controls=[
            action_row,
            ft.Container(
                content=tab_bar,
                padding=ft.Padding(
                    tokens.SPACE_MD, tokens.SPACE_XS, tokens.SPACE_MD, 0
                ),
            ),
            _document_container(),
            build_banner_ad(page),
            ft.Container(height=tokens.SPACE_XXXL * 3),
            focus_sink,
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    return ft.Stack(
        controls=[
            notebook_body,
            ft.Container(content=toolbar, bottom=0, left=0, right=0),
        ],
        expand=True,
    )


__all__ = ["NotebookView"]
