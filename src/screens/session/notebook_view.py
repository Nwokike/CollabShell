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
from core import constants, tokens
from core.stdin_hook import show_stdin_dialog
from core.styles import build_banner_ad
from screens.session.layout import build_keep_alive_card
from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx

logger = logging.getLogger("colab")

_MAX_OUTPUT_ENTRIES = 5000


@ft.component
def NotebookView(
    session_name: str,
    on_switch_terminal,
    register_actions=None,
    on_cells_change=None,
) -> ft.Control:
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    cells, set_cells = ft.use_state([])
    cells_ref = ft.use_ref([])
    save_debounce_ref = ft.use_ref(None)

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
        from services.ipynb_converter import ipynb_to_cells

        try:
            files = await page.file_picker.pick_files(
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["ipynb"],
                allow_multiple=False,
            )
            if files:
                fpath = files[0].path
                if fpath:
                    raw = Path(fpath).read_text(encoding="utf-8")
                    ipynb_data = json.loads(raw)
                    imported = ipynb_to_cells(ipynb_data)
                    _publish([CellData.from_dict(c) for c in imported])
                    _save()
                    controller.show_snack(
                        f"✅ Imported {len(imported)} cells from {files[0].name}"
                    )
        except Exception as ex:
            logger.exception("Import .ipynb failed")
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

    toolbar = build_notebook_toolbar(
        on_add_code=lambda e: _add_cell("code"),
        on_add_markdown=lambda e: _add_cell("markdown"),
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
            )
        )
        if (i + 1) % 2 == 0:
            cell_controls.append(build_banner_ad(page))

    notebook_body = ft.Column(
        controls=[
            keep_alive_card,
            ft.Container(
                content=ft.Column(controls=cell_controls, spacing=0),
                padding=ft.Padding(
                    tokens.SPACE_MD, 0, tokens.SPACE_MD, tokens.SPACE_XL
                ),
            ),
            build_banner_ad(page),
            ft.Container(height=tokens.SPACE_XXXL * 3),
        ],
        spacing=tokens.SPACE_SM,
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
