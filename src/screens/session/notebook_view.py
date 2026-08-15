"""NotebookView — Interactive notebook cell runner, outputs streaming, and IPYNB converter."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import flet as ft

from components.notebook_cell import build_notebook_cell
from components.notebook_toolbar import build_notebook_toolbar
from core import constants, tokens
from core.stdin_hook import show_stdin_dialog
from core.styles import build_banner_ad
from screens.session.layout import build_action_row, build_keep_alive_card
from screens.session.vm_ops import on_auth_gcp, on_mount_drive
from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx


@ft.component
def NotebookView(
    session_name: str, initial_mode: str, on_switch_terminal
) -> ft.Control:
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    cells, set_cells = ft.use_state([])
    cells_ref = ft.use_ref(None)
    output_ts_ref = ft.use_ref({})

    async def _load():
        loaded = await services.storage.load_notebook(session_name)
        if loaded:
            for c in loaded:
                c["is_running"] = False
            cells_ref.current = loaded
            set_cells(list(loaded))
        else:
            initial = [
                {
                    "id": str(uuid.uuid4()),
                    "type": "code",
                    "source": "",
                    "outputs": [],
                    "is_running": False,
                }
            ]
            cells_ref.current = initial
            set_cells(list(initial))

    ft.on_mounted(lambda: page.run_task(_load))

    # ── Persistence ───────────────────────────────────────────────────────────
    def _save():
        page.run_task(
            services.storage.save_notebook, session_name, cells_ref.current or []
        )

    # ── Cell output streaming (called thread-safely from background worker) ───
    def _append_output(index: int, text_or_dict):
        c_list = cells_ref.current
        if not c_list or index >= len(c_list):
            return
        cell = c_list[index]

        max_entries = 5000
        if len(cell["outputs"]) >= max_entries:
            cell["outputs"].pop(0)

        if isinstance(text_or_dict, str):
            cell["outputs"].append({"type": "stream", "text": text_or_dict})
        elif isinstance(text_or_dict, dict):
            cell["outputs"].append(text_or_dict)

        now = time.monotonic()
        ts_map = output_ts_ref.current
        last = ts_map.get(index, 0.0)
        if last == 0.0 or now - last >= 0.15:
            ts_map[index] = now
            set_cells(list(c_list))

    # ── Cell operations ───────────────────────────────────────────────────────
    async def _run_cell(idx: int):
        c_list = cells_ref.current
        if not c_list or idx >= len(c_list):
            return
        cell = c_list[idx]
        if cell["is_running"]:
            return

        cell["is_running"] = True
        cell["outputs"] = []
        set_cells(list(c_list))

        def _on_output(text_or_dict):
            page.loop.call_soon_threadsafe(_append_output, idx, text_or_dict)

        def _stdin_hook(prompt, *args, **kwargs):
            return show_stdin_dialog(page, prompt, *args, **kwargs)

        try:
            await services.colab.exec_code(
                cell["source"],
                session_name,
                timeout=float(state.default_timeout),
                auth_method=state.auth_method,
                on_output=_on_output,
                intercept_oauth=True,
                stdin_hook=_stdin_hook,
            )
        except Exception as ex:
            err = {"type": "error", "traceback": [str(ex)]}
            cell["outputs"].append(err)
        finally:
            cell["is_running"] = False
            set_cells(list(c_list))
            _save()

    def _stop_cell(idx: int):
        services.colab.cancel()
        c_list = cells_ref.current
        if c_list and 0 <= idx < len(c_list):
            c_list[idx]["outputs"].append(
                {"type": "error", "traceback": ["Execution cancelled by user"]}
            )
            c_list[idx]["is_running"] = False
            set_cells(list(c_list))
            _save()

    def _add_cell(cell_type: str):
        c_list = list(cells_ref.current or [])
        c_list.append(
            {
                "id": str(uuid.uuid4()),
                "type": cell_type,
                "source": "",
                "outputs": [],
                "is_running": False,
            }
        )
        cells_ref.current = c_list
        set_cells(c_list)
        _save()

    def _delete_cell(idx: int):
        c_list = list(cells_ref.current or [])
        if 0 <= idx < len(c_list):
            c_list.pop(idx)
            cells_ref.current = c_list
            set_cells(c_list)
            _save()

    def _move_cell(idx: int, direction: int):
        c_list = list(cells_ref.current or [])
        new_idx = idx + direction
        if 0 <= new_idx < len(c_list):
            c_list[idx], c_list[new_idx] = c_list[new_idx], c_list[idx]
            cells_ref.current = c_list
            set_cells(c_list)
            _save()

    def _clear_cell(idx: int):
        c_list = cells_ref.current
        if c_list and 0 <= idx < len(c_list):
            c_list[idx]["outputs"] = []
            set_cells(list(c_list))
            _save()

    def _clear_all_outputs(e=None):
        c_list = cells_ref.current or []
        for cell in c_list:
            cell["outputs"] = []
        set_cells(list(c_list))
        _save()

    def _on_source_change(idx: int, value: str):
        c_list = cells_ref.current
        if c_list and 0 <= idx < len(c_list):
            c_list[idx]["source"] = value
            _save()

    # ── IPYNB export / import ─────────────────────────────────────────────────
    async def _export_ipynb(e=None):
        from services.ipynb_converter import cells_to_ipynb

        c_list = cells_ref.current or []
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
                controller.show_snack(f"❌ Export failed: {ex}")

    async def _import_ipynb(e=None):
        from services.ipynb_converter import ipynb_to_cells

        files = await page.file_picker.pick_files(
            allowed_extensions=["ipynb"],
            with_data=bool(getattr(page, "web", False)),
        )
        if not files:
            return
        try:
            picked = files[0]
            raw = (
                picked.bytes
                if picked.bytes is not None
                else Path(picked.path).read_bytes()
            )
            ipynb = json.loads(raw)
            imported_cells = ipynb_to_cells(ipynb)
            cells_ref.current = imported_cells
            set_cells(list(imported_cells))
            _save()
            controller.show_snack(f"✅ Imported {len(imported_cells)} cell(s)")
        except Exception as ex:
            controller.show_snack(f"❌ Import failed: {ex}")

    # ── VM operations ─────────────────────────────────────────────────────────
    def _stdin_hook(prompt, *args, **kwargs):
        return show_stdin_dialog(page, prompt, *args, **kwargs)

    async def _on_mount_drive(e=None):
        await on_mount_drive(
            page,
            session_name,
            services.colab,
            state,
            snack=controller.show_snack,
            stdin_hook=_stdin_hook,
        )

    async def _on_auth_gcp(e=None):
        await on_auth_gcp(
            page,
            session_name,
            services.colab,
            state,
            snack=controller.show_snack,
            stdin_hook=_stdin_hook,
        )

    async def _on_open_browser(e=None):
        try:
            url = await services.colab.get_session_url(
                session_name, auth_method=state.auth_method
            )
            await ft.UrlLauncher().launch_url(url)
        except Exception as ex:
            controller.show_snack(f"Error: {ex}")

    async def _do_restart():
        state.is_executing = False
        try:
            await services.colab.restart_session(
                session_name, auth_method=state.auth_method
            )
            controller.show_snack("✅ Kernel restarted")
        except Exception as ex:
            controller.show_snack(f"❌ Restart failed: {ex}")

    def _on_restart(e=None):
        # Confirm before firing — all variables will be lost
        session_exists = any(
            s.get("name") == session_name for s in state.active_sessions
        )
        if not session_exists:
            controller.show_snack("Session is no longer available.")
            return

        def _close(ev=None):
            page.pop_dialog()

        def _confirm_restart(ev):
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
                    ft.FilledButton("Restart", on_click=_confirm_restart),
                ],
            )
        )

    async def _do_stop():
        try:
            await services.colab.stop_session(
                session_name, auth_method=state.auth_method
            )
            controller.show_snack("✅ Session terminated")
            state.active_sessions = await services.colab.list_sessions(
                auth_method=state.auth_method
            )
            controller.close_session()
        except Exception as ex:
            controller.show_snack(f"❌ Stop failed: {ex}")

    def _on_stop(e=None):
        # Confirm before firing — resources will be released
        session_exists = any(
            s.get("name") == session_name for s in state.active_sessions
        )
        if not session_exists:
            controller.show_snack("Session is no longer available.")
            return

        def _close(ev=None):
            page.pop_dialog()

        def _confirm_stop(ev):
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
                    ft.FilledButton("Stop", on_click=_confirm_stop),
                ],
            )
        )

    async def _on_keep_alive(e):
        state.keep_alive_enabled = e.control.value
        await services.storage.set(
            constants.STORAGE_KEEP_ALIVE, str(e.control.value).lower()
        )

    async def _on_keep_alive_disconnect(e):
        state.keep_alive_on_disconnect = e.control.value
        await services.storage.set(
            constants.STORAGE_KEEP_ALIVE_ON_DISCONNECT,
            str(e.control.value).lower(),
        )

    # ── Action row ────────────────────────────────────────────────────────────
    action_row = build_action_row(
        page=page,
        on_files=lambda e: controller.open_session(session_name, "files"),
        on_mount_drive=lambda e: page.run_task(_on_mount_drive, e),
        on_auth_gcp=lambda e: page.run_task(_on_auth_gcp, e),
        on_open_browser=lambda e: page.run_task(_on_open_browser, e),
        on_terminal=lambda e: on_switch_terminal(),
        on_view_logs=lambda e: None,
        on_restart=lambda e: _on_restart(e),
        on_stop=lambda e: _on_stop(e),
    )

    keep_alive_card = build_keep_alive_card(
        page=page,
        state=state,
        on_keep_alive=lambda e: page.run_task(_on_keep_alive, e),
        on_keep_alive_disconnect=lambda e: page.run_task(_on_keep_alive_disconnect, e),
    )

    toolbar = build_notebook_toolbar(
        on_add_code=lambda e: _add_cell("code"),
        on_add_markdown=lambda e: _add_cell("markdown"),
        on_clear_all=_clear_all_outputs,
        on_export_ipynb=lambda e: page.run_task(_export_ipynb, e),
        on_import_ipynb=lambda e: page.run_task(_import_ipynb, e),
        on_open_terminal=on_switch_terminal,
    )

    # ── Render cells ──────────────────────────────────────────────────────────
    cell_controls = []
    for i, cell in enumerate(cells):
        container, _ = build_notebook_cell(
            page,
            cell,
            on_run=lambda idx=i: page.run_task(_run_cell, idx),
            on_stop=lambda idx=i: _stop_cell(idx),
            on_delete=lambda idx=i: _delete_cell(idx),
            on_move_up=lambda idx=i: _move_cell(idx, -1),
            on_move_down=lambda idx=i: _move_cell(idx, 1),
            on_change=lambda value, idx=i: _on_source_change(idx, value),
            on_clear_output=lambda idx=i: _clear_cell(idx),
            on_open_terminal=on_switch_terminal,
        )
        cell_controls.append(container)
        if (i + 1) % 2 == 0:
            cell_controls.append(build_banner_ad(page))

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
