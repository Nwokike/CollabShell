"""SessionScreen — Notebook and Terminal tabs for a running Colab session.

Architecture notes:
- `cells` state holds the full list of cell dicts (type, source, outputs, is_running).
- Each NotebookCell component owns its own view; the parent coordinates cell operations.
- `append_output_to_cell` fires from a background thread via page.loop.call_soon_threadsafe.
- The terminal tab lazily initializes on first switch.
"""

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
from screens.session.layout import (
    build_action_row,
    build_keep_alive_card,
    build_status_header,
)
from screens.session.terminal_panel import build_terminal_panel
from screens.session.vm_ops import on_auth_gcp, on_mount_drive
from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx

# ── NotebookView ──────────────────────────────────────────────────────────────


@ft.component
def NotebookView(
    session_name: str, initial_mode: str, on_switch_terminal
) -> ft.Control:
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    cells, set_cells = ft.use_state([])
    # Stable ref so background threads can always append without stale closure
    cells_ref = ft.use_ref(None)
    output_ts_ref = ft.use_ref({})  # {index: float} throttle timestamps

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

    # ── Cell output streaming (called from background thread) ─────────────────
    def _append_output(index: int, text_or_dict):
        """Append streaming output to a cell. Safe to call from any thread."""
        c_list = cells_ref.current
        if not c_list or index >= len(c_list):
            return
        cell = c_list[index]

        _MAX = 5000
        if len(cell["outputs"]) >= _MAX:
            cell["outputs"].pop(0)

        if isinstance(text_or_dict, str):
            cell["outputs"].append({"type": "stream", "text": text_or_dict})
        elif isinstance(text_or_dict, dict):
            cell["outputs"].append(text_or_dict)

        # Throttled UI update — at most every 150 ms per cell
        now = time.monotonic()
        ts_map = output_ts_ref.current
        last = ts_map.get(index, 0.0)
        if last == 0.0 or now - last >= 0.15:
            ts_map[index] = now
            set_cells(list(c_list))  # triggers re-render

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
                    allowed_extensions=["ipynb"], file_name=f"{session_name}.ipynb"
                )
            except ValueError:
                dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                os.makedirs(dl_dir, exist_ok=True)
                path = os.path.join(dl_dir, f"{session_name}.ipynb")
        if path:
            try:
                ipynb = cells_to_ipynb(c_list)
                Path(path).write_text(
                    json.dumps(ipynb, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                controller.show_snack("✅ Notebook exported")
            except Exception as ex:
                controller.show_snack(f"❌ Export failed: {ex}")

    async def _import_ipynb(e=None):
        from services.ipynb_converter import ipynb_to_cells

        files = await page.file_picker.pick_files(
            allowed_extensions=["ipynb"], with_data=bool(getattr(page, "web", False))
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

    async def _on_restart(e=None):
        state.is_executing = False
        try:
            await services.colab.restart_session(
                session_name, auth_method=state.auth_method
            )
            controller.show_snack("✅ Session restarted")
        except Exception as ex:
            controller.show_snack(f"❌ Restart failed: {ex}")

    async def _on_stop(e=None):
        try:
            await services.colab.stop_session(
                session_name, auth_method=state.auth_method
            )
            controller.show_snack("✅ Session stopped")
            state.active_sessions = await services.colab.list_sessions(
                auth_method=state.auth_method
            )
            controller.close_session()
        except Exception as ex:
            controller.show_snack(f"❌ Stop failed: {ex}")

    async def _on_keep_alive(e):
        state.keep_alive_enabled = e.control.value
        await services.storage.set(
            constants.STORAGE_KEEP_ALIVE, str(e.control.value).lower()
        )

    async def _on_keep_alive_disconnect(e):
        state.keep_alive_on_disconnect = e.control.value
        await services.storage.set(
            constants.STORAGE_KEEP_ALIVE_ON_DISCONNECT, str(e.control.value).lower()
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
        on_restart=lambda e: page.run_task(_on_restart, e),
        on_stop=lambda e: page.run_task(_on_stop, e),
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


# ── SessionScreen ─────────────────────────────────────────────────────────────


@ft.component
def SessionScreen(session_name: str, mode: str, on_back) -> ft.Control:
    """Top-level session screen with Notebook/Terminal tab switching."""
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    active_tab, set_tab = ft.use_state(0 if mode == "notebook" else 1)
    terminal_ready, set_terminal_ready = ft.use_state(mode == "terminal")
    terminal_init_ref = ft.use_ref(None)

    def _switch_to_terminal():
        if not terminal_ready:
            set_terminal_ready(True)
        set_tab(1)

    ft.use_effect(
        lambda: (
            page.run_task(terminal_init_ref.current)
            if terminal_ready and terminal_init_ref.current
            else None
        ),
        [terminal_ready],
    )

    # ── Terminal panel (built once on first access) ───────────────────────────
    if terminal_ready:
        terminal_panel, terminal_init_func = build_terminal_panel(
            page,
            session_name,
            services.colab,
            snack=controller.show_snack,
        )
        terminal_init_ref.current = terminal_init_func
    else:
        terminal_panel = ft.Container()

    # ── Status header ─────────────────────────────────────────────────────────
    status_header = build_status_header(
        page=page, session_name=session_name, state=state, colab_service=services.colab
    )

    # ── Tab bar ───────────────────────────────────────────────────────────────
    def _on_tab_change(e):
        idx = int(e.data) if e and e.data else 0
        if idx == 1 and not terminal_ready:
            set_terminal_ready(True)
        set_tab(idx)

    tab_bar = ft.Tabs(
        selected_index=active_tab,
        on_change=_on_tab_change,
        expand=False,
        tabs=[
            ft.Tab(
                text="Notebook",
                icon=ft.Icons.EDIT_NOTE_ROUNDED,
            ),
            ft.Tab(
                text="Terminal",
                icon=ft.Icons.TERMINAL_ROUNDED,
            ),
        ],
    )

    # ── Content area ──────────────────────────────────────────────────────────
    content = ft.Stack(
        controls=[
            ft.Container(
                content=NotebookView(
                    session_name=session_name,
                    initial_mode=mode,
                    on_switch_terminal=_switch_to_terminal,
                ),
                expand=True,
                visible=active_tab == 0,
            ),
            ft.Container(
                content=terminal_panel,
                expand=True,
                visible=active_tab == 1,
            ),
        ],
        expand=True,
    )

    header_bar = ft.Container(
        content=ft.Row(
            controls=[
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    on_click=lambda e: on_back(),
                    icon_size=tokens.ICON_MD,
                    tooltip="Back to Home",
                ),
                ft.Text(
                    "Active Session", size=tokens.FONT_LG, weight=ft.FontWeight.W_700
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(
            tokens.SPACE_SM, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM
        ),
        bgcolor=ft.Colors.SURFACE,
    )

    return ft.Column(
        controls=[
            header_bar,
            status_header,
            tab_bar,
            content,
        ],
        spacing=0,
        expand=True,
    )
