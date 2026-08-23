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
from pathlib import Path

import flet as ft

from components.notebook_cell import CellData, NotebookCell
from components.notebook_toolbar import build_notebook_toolbar
from components.shortcuts_help import open_shortcuts_help
from core import constants, tokens
from core.shortcuts import Binding
from core.stdin_hook import show_stdin_dialog
from core.styles import build_banner_ad
from screens.files.modal import show_manage_files_modal
from screens.session.layout import build_action_row, build_keep_alive_card
from screens.session.vm_ops import on_auth_gcp, on_mount_drive
from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx

logger = logging.getLogger("colab")

_MAX_OUTPUT_ENTRIES = 5000


@ft.component
def NotebookView(
    session_name: str,
    on_switch_terminal,
    register_actions=None,
    on_cells_change=None,
    register_bindings=None,
) -> ft.Control:
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    cells, set_cells = ft.use_state([])
    cells_ref = ft.use_ref([])
    save_debounce_ref = ft.use_ref(None)
    # ── Active-cell model (keyboard shortcuts) ───────────────────────────────
    # The active cell is the last one whose editor held focus (sticky — it
    # survives blur, matching Jupyter's selection model). Run/move/delete
    # shortcuts target it. focus_req is (cell_id, counter): bumping the
    # counter asks that cell's editor to grab focus after the next render.
    active_cell_id, set_active_cell_id = ft.use_state("")
    focus_req, set_focus_req = ft.use_state(("", 0))
    focus_sink_ref = ft.use_ref(None)

    def _publish(new_list: list):
        cells_ref.current = new_list
        set_cells(list(new_list))
        if on_cells_change:
            on_cells_change(len(new_list))

    async def _load():
        loaded = await services.storage.load_notebook(session_name)
        if loaded:
            _publish([CellData.from_dict(c) for c in loaded])
        else:
            _publish([CellData()])

    ft.on_mounted(lambda: page.run_task(_load))

    # ── Persistence ───────────────────────────────────────────────────────────
    def _save():
        try:
            if getattr(page, "_session", getattr(page, "session", None)):
                page.run_task(
                    services.storage.save_notebook,
                    session_name,
                    [c.to_dict() for c in cells_ref.current or []],
                )
        except RuntimeError:
            pass

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
            _save()

    ft.on_unmounted(_flush_pending_save)

    # ── Output streaming ──────────────────────────────────────────────────────
    def _append_output(cell: CellData, text_or_dict):
        entry = (
            text_or_dict
            if isinstance(text_or_dict, dict)
            else {"type": "stream", "text": str(text_or_dict)}
        )
        if len(cell.outputs) >= _MAX_OUTPUT_ENTRIES:
            cell.outputs.pop(0)
        cell.outputs.append(entry)
        cell.outputs_rev += 1

    # ── Cell execution ────────────────────────────────────────────────────────
    async def _run_cell(cell: CellData):
        if cell.is_running:
            return
        cell.is_running = True
        cell.outputs.clear()
        cell.outputs_rev += 1

        def _on_output(text_or_dict):
            page.loop.call_soon_threadsafe(_append_output, cell, text_or_dict)

        def _stdin_hook(prompt, *args, **kwargs):
            return show_stdin_dialog(
                page, prompt, controller.show_snack, *args, **kwargs
            )

        try:
            await services.colab.exec_code(
                cell.source,
                session_name,
                timeout=float(state.default_timeout),
                auth_method=state.auth_method,
                on_output=_on_output,
                intercept_oauth=True,
                stdin_hook=_stdin_hook,
            )
        except Exception as ex:
            _append_output(cell, {"type": "error", "traceback": [str(ex)]})
        finally:
            cell.is_running = False
            _save()

    def _stop_cell(cell: CellData):
        services.colab.cancel()
        _append_output(
            cell, {"type": "error", "traceback": ["Execution cancelled by user"]}
        )
        cell.is_running = False
        _save()

    # ── Cell list operations ──────────────────────────────────────────────────
    def _add_cell(cell_type: str):
        c_list = list(cells_ref.current or [])
        c_list.append(CellData(cell_type=cell_type))
        _publish(c_list)
        _save()

    def _delete_cell(cell: CellData):
        c_list = [c for c in cells_ref.current or [] if c.id != cell.id]
        _publish(c_list)
        _save()

    def _move_cell(cell: CellData, direction: int):
        c_list = list(cells_ref.current or [])
        idx = next((i for i, c in enumerate(c_list) if c.id == cell.id), -1)
        new_idx = idx + direction
        if idx < 0 or not 0 <= new_idx < len(c_list):
            return
        c_list[idx], c_list[new_idx] = c_list[new_idx], c_list[idx]
        _publish(c_list)
        _save()

    def _clear_cell_output(cell: CellData):
        cell.outputs.clear()
        cell.outputs_rev += 1
        _save()

    # ── Active-cell operations (keyboard shortcuts) ──────────────────────────
    def _active_cell() -> CellData | None:
        c_list = cells_ref.current or []
        for c in c_list:
            if c.id == active_cell_id:
                return c
        return c_list[-1] if c_list else None

    def _focus_cell(cell_id: str):
        set_focus_req((cell_id, (focus_req[1] or 0) + 1))

    def _on_cell_focus(cell_id: str, focused: bool):
        if focused and cell_id != active_cell_id:
            set_active_cell_id(cell_id)

    def _insert_cell_near(above: bool, after_id: str | None = None):
        """Insert a code cell above/below the active cell (or at the end)."""
        c_list = list(cells_ref.current or [])
        anchor_id = after_id or active_cell_id
        anchor_idx = next(
            (i for i, c in enumerate(c_list) if c.id == anchor_id), -1
        )
        new_cell = CellData(cell_type="code")
        if anchor_idx == -1:
            c_list.append(new_cell)
        else:
            c_list.insert(anchor_idx if above else anchor_idx + 1, new_cell)
        _publish(c_list)
        _save()
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
        for cell in list(cells_ref.current or []):
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
        c_list = list(cells_ref.current or [])
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
        for cell in cells_ref.current or []:
            cell.outputs.clear()
            cell.outputs_rev += 1
        _save()

    # ── IPYNB export / import ─────────────────────────────────────────────────
    async def _export_ipynb(e=None):
        from services.ipynb_converter import cells_to_ipynb

        c_list = [c.to_dict() for c in cells_ref.current or []]
        if page.platform.is_mobile():
            dl_dir = "/storage/emulated/0/Download"
            if not os.path.exists(dl_dir):
                dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(dl_dir, exist_ok=True)
            path = os.path.join(dl_dir, f"{session_name}.ipynb")
        else:
            try:
                path = await page.file_picker.save_file(
                    allowed_extensions=["ipynb"],
                    file_name=f"{session_name}.ipynb",
                )
            except ValueError:
                dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                os.makedirs(dl_dir, exist_ok=True)
                path = os.path.join(dl_dir, f"{session_name}.ipynb")
        if path:
            try:
                ipynb = cells_to_ipynb(c_list)
                Path(path).write_text(
                    json.dumps(ipynb, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                controller.show_snack("✅ Notebook exported")
            except Exception as ex:
                controller.show_snack(f"❌ Export failed: {ex}", is_error=True)

    async def _import_ipynb(e=None):
        """Import a `.ipynb` notebook, or a `.py` script (becomes code cells)."""
        from services.ipynb_converter import ipynb_to_cells, py_to_cells

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
                    _publish([CellData.from_dict(c) for c in imported])
                    _save()
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
                "export_ipynb": lambda: page.run_task(_export_ipynb),
                "import_ipynb": lambda: page.run_task(_import_ipynb),
                "clear_all": _clear_all_outputs,
            }
        )

    # Refresh the shortcut binding table every render so the router always
    # sees current closures (cells, handlers). Writing to the session's ref
    # is side-effect free — no re-render loop.
    if register_bindings:
        register_bindings(
            [
                (Binding("Enter", ctrl=True, shift=True), lambda: page.run_task(_run_all)),
                (Binding("Enter", shift=True), lambda: _shortcut_run("next")),
                (Binding("Enter", alt=True), lambda: _shortcut_run("insert")),
                (Binding("Enter", ctrl=True), lambda: _shortcut_run("inplace")),
                (Binding("s", ctrl=True), lambda: page.run_task(_export_ipynb)),
                (Binding("a", ctrl=True, shift=True), lambda: _insert_cell_near(True)),
                (Binding("b", ctrl=True, shift=True), lambda: _insert_cell_near(False)),
                (Binding("ArrowUp", alt=True), lambda: _move_active(-1)),
                (Binding("ArrowDown", alt=True), lambda: _move_active(1)),
                (Binding("d", ctrl=True, shift=True), _delete_active),
                (Binding("m", ctrl=True, shift=True), _toggle_active_type),
                (Binding("Escape"), _blur_editor),
                (Binding("F1"), lambda: open_shortcuts_help(page, "notebook")),
            ]
        )

    # ── Keep-alive & Action row ───────────────────────────────────────────────
    async def _on_toggle_keep_alive(e):
        val = e.control.value
        state.keep_alive_enabled = val
        await services.storage.set(
            constants.STORAGE_KEEP_ALIVE, "true" if val else "false"
        )
        page.update()

    async def _on_toggle_keep_alive_dc(e):
        val = e.control.value
        state.keep_alive_on_disconnect = val
        await services.storage.set(
            constants.STORAGE_KEEP_ALIVE_ON_DISCONNECT, "true" if val else "false"
        )
        page.update()

    keep_alive_card = build_keep_alive_card(
        page, state, _on_toggle_keep_alive, _on_toggle_keep_alive_dc
    )

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
    )

    toolbar = build_notebook_toolbar(
        on_add_code=lambda e: _add_cell("code"),
        on_add_markdown=lambda e: _add_cell("markdown"),
        on_export_ipynb=lambda e: page.run_task(_export_ipynb, e),
        on_import_ipynb=lambda e: page.run_task(_import_ipynb, e),
    )

    # ── Render cells ──────────────────────────────────────────────────────────
    cell_controls = []
    for i, cell in enumerate(cells):
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
            )
        )
        if (i + 1) % 2 == 0:
            cell_controls.append(build_banner_ad(page))

    # Invisible focusable sink — Escape moves focus here so editors blur and
    # markdown cells render (kept 1px, not 0, so the focus node stays live).
    focus_sink = ft.KeyboardListener(
        content=ft.Container(width=1, height=1, content=ft.Container(width=0, height=0)),
        ref=focus_sink_ref,
    )


    notebook_body = ft.Column(
        controls=[
            keep_alive_card,
            action_row,
            ft.Container(
                content=ft.Column(controls=cell_controls, spacing=0),
                padding=ft.Padding(
                    tokens.SPACE_MD, 0, tokens.SPACE_MD, tokens.SPACE_XL
                ),
            ),
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
