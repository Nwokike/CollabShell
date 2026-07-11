"""Session detail view — full control over an active session."""

from __future__ import annotations

import asyncio
import json
import time
import flet as ft
import threading
import uuid
from pathlib import Path

from core import tokens, constants
from core.styles import (
    glass_card,
    hardware_badge,
    status_dot,
    build_banner_ad,
)
from core.theme import AppColors
from components.notebook_cell import build_notebook_cell
from components.notebook_toolbar import build_notebook_toolbar
from services.storage_service import StorageService
from services.ipynb_converter import cells_to_ipynb, ipynb_to_cells


def build_session_view(
    page: ft.Page,
    colab_service,
    state,
    session_name: str,
    on_back=None,
    navigate=None,
    snack=None,
    theme_btn=None,
    storage: StorageService = None,
) -> ft.View:
    if storage is None:
        storage = StorageService(page)

    if not hasattr(state, "notebook_cells"):
        state.notebook_cells = []

    session = next(
        (s for s in state.active_sessions if s.get("name") == session_name), None
    )

    if not session:
        content_err = ft.Column(
            controls=[
                ft.AppBar(
                    leading=ft.IconButton(
                        ft.Icons.ARROW_BACK_ROUNDED, on_click=on_back
                    ),
                    title=ft.Text("Session Not Found"),
                ),
                ft.Container(
                    content=ft.Text(
                        constants.ERR_NO_SESSION, color=ft.Colors.ON_SURFACE_VARIANT
                    ),
                    padding=tokens.SPACE_XL,
                    alignment=ft.Alignment.CENTER,
                ),
            ],
            expand=True,
        )
        return ft.View(f"/session?session={session_name}", [content_err], padding=0)

    accel = session.get("accelerator", "NONE")
    variant = session.get("variant", "DEFAULT")
    is_running = session.get("running") is not None

    # ── Status header ─────────────────────────────────────────────────────────
    status_header = glass_card(
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        status_dot(is_running),
                        ft.Text(
                            session_name,
                            size=tokens.FONT_XL,
                            weight=ft.FontWeight.W_700,
                            expand=True,
                        ),
                        hardware_badge(accel, variant),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=tokens.SPACE_MD,
                ),
                ft.Text(
                    session.get("status", "IDLE"),
                    size=tokens.FONT_SM,
                    color=AppColors.SUCCESS
                    if is_running
                    else ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM
        ),
    )

    # ── Action Row (Compact) ─────────────────────────────────────────────────
    async def _navigate_home(msg=None):
        if msg and snack:
            snack(msg)
        if on_back:
            on_back(None)

    async def _check_session():
        if not session:
            await _navigate_home("Session has expired.")
            return False
        return True

    async def _on_files(e):
        if not await _check_session():
            return
        if navigate:
            await navigate(f"/files?session={session_name}")

    async def _on_open_browser(e):
        if not await _check_session():
            return
        try:
            url = await colab_service.get_session_url(
                session_name, auth_method=state.auth_method
            )
            await ft.UrlLauncher().launch_url(url)
        except Exception as ex:
            if snack:
                snack(f"Error: {ex}")

    async def _on_restart(e):
        if not await _check_session():
            return

        def _close_and_restart(ev):
            page.pop_dialog()
            page.run_task(_do_restart)

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Restart Kernel?"),
                content=ft.Text(
                    "This will restart the Python kernel. All variables will be lost."
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton("Restart", on_click=_close_and_restart),
                ],
            )
        )

    async def _do_restart():
        if snack:
            snack("Restarting kernel...")
        try:
            await colab_service.restart_kernel(
                session_name, auth_method=state.auth_method
            )
            if snack:
                snack("✅ Kernel restarted")
        except Exception as ex:
            if snack:
                snack(f"❌ {ex}")

    async def _on_stop(e):
        if not await _check_session():
            return

        def _close_and_stop(ev):
            page.pop_dialog()
            page.run_task(_do_stop)

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Stop Session?"),
                content=ft.Text(
                    "This will terminate the session and release all resources."
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton("Stop", on_click=_close_and_stop),
                ],
            )
        )

    async def _do_stop():
        if snack:
            snack("Stopping session...")
        try:
            await colab_service.stop_session(
                session_name, auth_method=state.auth_method
            )
            if snack:
                snack("✅ Session terminated")
            state.active_sessions = await colab_service.list_sessions(
                auth_method=state.auth_method
            )
            if on_back:
                on_back(None)
        except Exception as ex:
            if snack:
                snack(f"❌ {ex}")

    async def _on_mount_drive(e):
        if snack:
            snack("Mounting Google Drive...")
        try:
            await colab_service.mount_drive(
                session_name, path=state.drive_mount_path, auth_method=state.auth_method
            )
            if snack:
                snack("✅ Drive mounted")
        except Exception as ex:
            if snack:
                snack(f"❌ {ex}")

    async def _on_auth_gcp(e):
        if snack:
            snack("Authenticating with GCP on VM...")
        try:
            await colab_service.auth_gcp_on_vm(
                session_name, auth_method=state.auth_method
            )
            if snack:
                snack("✅ GCP auth complete")
        except Exception as ex:
            if snack:
                snack(f"❌ {ex}")

    async def _on_view_logs(e):
        if navigate:
            await navigate(f"/history?session={session_name}")

    # ── Keep-Alive Toggles ─────────────────────────────────────────────────────
    async def _on_keep_alive(e):
        state.keep_alive_enabled = e.control.value
        await storage.set(constants.STORAGE_KEEP_ALIVE, str(e.control.value).lower())

    async def _on_keep_alive_disconnect(e):
        state.keep_alive_on_disconnect = e.control.value
        await storage.set(
            constants.STORAGE_KEEP_ALIVE_ON_DISCONNECT,
            str(e.control.value).lower(),
        )

    # ── IPYNB Export/Import ────────────────────────────────────────────────────
    _pending_file_op = None

    def _on_file_result(e: ft.FilePickerResultEvent):
        nonlocal _pending_file_op
        op = _pending_file_op
        _pending_file_op = None

        if op == "export" and e.path:
            try:
                ipynb = cells_to_ipynb(state.notebook_cells)
                Path(e.path).write_text(
                    json.dumps(ipynb, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                if snack:
                    snack("✅ Notebook exported")
            except Exception as ex:
                if snack:
                    snack(f"❌ Export failed: {ex}")

        elif op == "import" and e.files:
            try:
                path = e.files[0].path
                raw = Path(path).read_bytes()
                ipynb = json.loads(raw)
                cells = ipynb_to_cells(ipynb)
                state.notebook_cells = cells
                _rebuild_cells()
                _save_notebook()
                if snack:
                    snack(f"✅ Imported {len(cells)} cell(s)")
            except Exception as ex:
                if snack:
                    snack(f"❌ Import failed: {ex}")

    page.file_picker.on_result = _on_file_result
    page.update()

    def _on_export_ipynb(e):
        nonlocal _pending_file_op
        _pending_file_op = "export"
        page.file_picker.save_file(
            allowed_extensions=["ipynb"],
            file_name=f"{session_name}.ipynb",
        )

    def _on_import_ipynb(e):
        nonlocal _pending_file_op
        _pending_file_op = "import"
        page.file_picker.pick_files(
            allowed_extensions=["ipynb"],
        )

    def _action_chip(icon, label, on_click, color=None):
        icon_color = color or ft.Colors.ON_SURFACE
        return ft.FilledButton(
            content=ft.Row(
                [
                    ft.Icon(icon, size=tokens.ICON_SM, color=icon_color),
                    ft.Text(label, size=tokens.FONT_XS, color=ft.Colors.ON_SURFACE),
                ],
                spacing=tokens.SPACE_XS,
            ),
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE),
                elevation=0,
            ),
            on_click=on_click,
            height=32,
        )

    action_row = ft.Container(
        content=ft.Row(
            controls=[
                _action_chip(
                    ft.Icons.FOLDER_ROUNDED,
                    "Files",
                    lambda e: page.run_task(_on_files, e),
                ),
                _action_chip(
                    ft.Icons.ADD_TO_DRIVE_ROUNDED,
                    "Mount Drive",
                    lambda e: page.run_task(_on_mount_drive, e),
                ),
                _action_chip(
                    ft.Icons.SECURITY_ROUNDED,
                    "Auth GCP",
                    lambda e: page.run_task(_on_auth_gcp, e),
                ),
                _action_chip(
                    ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                    "Browser",
                    lambda e: page.run_task(_on_open_browser, e),
                    AppColors.BADGE_TPU,
                ),
                _action_chip(
                    ft.Icons.HISTORY_ROUNDED,
                    "Logs",
                    lambda e: page.run_task(_on_view_logs, e),
                ),
                _action_chip(
                    ft.Icons.REFRESH_ROUNDED,
                    "Restart",
                    lambda e: page.run_task(_on_restart, e),
                    AppColors.WARNING,
                ),
                _action_chip(
                    ft.Icons.STOP_CIRCLE_ROUNDED,
                    "Stop",
                    lambda e: page.run_task(_on_stop, e),
                    AppColors.ERROR,
                ),
            ],
            scroll=ft.ScrollMode.HIDDEN,
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
    )

    # ── Notebook Cells ────────────────────────────────────────────────────────
    cells_list = ft.Column(spacing=0)
    cell_refs = []
    _rebuild_throttle = 0.0
    _output_update_ts = {}

    async def _deferred_update():
        """Yield to the event loop then push the update — fixes mobile rendering."""
        await asyncio.sleep(0)
        page.update()

    def _save_notebook():
        page.run_task(storage.save_notebook, session_name, state.notebook_cells)

    # ── Targeted per-cell helpers ─────────────────────────────────────────────

    def _set_cell_running(index):
        if index >= len(cell_refs):
            return
        refs = cell_refs[index]
        play = refs["play_btn"].current
        stop = refs["stop_row"].current
        if play:
            play.visible = False
        if stop:
            stop.visible = True
        out = refs["output"].current
        if out:
            out.visible = True
        page.run_task(_deferred_update)

    def _set_cell_finished(index):
        if index >= len(cell_refs):
            return
        refs = cell_refs[index]
        play = refs["play_btn"].current
        stop = refs["stop_row"].current
        if play:
            play.visible = True
        if stop:
            stop.visible = False
        page.run_task(_deferred_update)

    def _append_cell_output(index, text_or_dict):
        if index >= len(cell_refs):
            return
        refs = cell_refs[index]

        # Try xterm terminal first
        terminal = refs.get("terminal")
        if terminal is not None:
            text = ""
            if isinstance(text_or_dict, str):
                text = text_or_dict
            elif isinstance(text_or_dict, dict):
                dtype = text_or_dict.get("type", "")
                if dtype == "stream":
                    text = text_or_dict.get("text", "")
                elif dtype == "error":
                    text = "\n".join(text_or_dict.get("traceback", []))
                else:
                    return
            if not text:
                return
            # Convert \n to \r\n for xterm
            text = text.replace("\r\n", "\n").replace("\n", "\r\n")
            terminal.write(text)
            # Make output panel visible
            out_col = refs["output"].current
            if out_col:
                out_col.visible = True
            now = time.monotonic()
            last = _output_update_ts.get(index, 0.0)
            if now - last >= 0.15:
                _output_update_ts[index] = now
                page.run_task(_deferred_update)
            return

        # Fallback: text-based output
        out_col = refs["output"].current
        if not out_col:
            return
        text = ""
        is_err = False
        if isinstance(text_or_dict, str):
            text = text_or_dict
        elif isinstance(text_or_dict, dict):
            dtype = text_or_dict.get("type", "")
            if dtype == "stream":
                text = text_or_dict.get("text", "")
                is_err = text_or_dict.get("name") == "stderr"
            elif dtype == "error":
                text = "\n".join(text_or_dict.get("traceback", []))
                is_err = True
            else:
                return
        if not text:
            return
        from components.ansi_parser import parse_ansi_to_flet_text

        out_col.controls.append(
            parse_ansi_to_flet_text(
                raw_text=text, default_size=tokens.FONT_SM, is_error=is_err
            )
        )
        out_col.visible = True
        now = time.monotonic()
        last = _output_update_ts.get(index, 0.0)
        if now - last >= 0.15:
            _output_update_ts[index] = now
            page.run_task(_deferred_update)

    def _clear_cell_output(index):
        if index >= len(cell_refs):
            return
        refs = cell_refs[index]
        # Clear xterm terminal if available
        terminal = refs.get("terminal")
        if terminal is not None:
            terminal.clear()
        out_col = refs["output"].current
        if out_col:
            out_col.controls.clear()
            out_col.visible = False
            page.run_task(_deferred_update)

    # ── Rebuild all cells (structural changes only) ───────────────────────────

    def _rebuild_cells(force=False):
        nonlocal _rebuild_throttle, cell_refs
        now = time.monotonic()
        if not force and now - _rebuild_throttle < 0.15:
            return
        _rebuild_throttle = now
        cell_refs.clear()
        cells_list.controls.clear()
        for i, cell in enumerate(state.notebook_cells):
            container, refs = build_notebook_cell(page, cell, **make_callbacks(i))
            cells_list.controls.append(container)
            cell_refs.append(refs)
        page.run_task(_deferred_update)

    def _stop_cell(idx):
        if 0 <= idx < len(state.notebook_cells):
            colab_service.cancel()
            cell = state.notebook_cells[idx]
            cell["outputs"].append(
                {"type": "error", "traceback": ["Execution cancelled by user"]}
            )
            cell["is_running"] = False
            _append_cell_output(
                idx, {"type": "error", "traceback": ["Execution cancelled by user"]}
            )
            _set_cell_finished(idx)
            _save_notebook()

    def make_callbacks(idx):
        def _clear():
            state.notebook_cells[idx]["outputs"] = []
            _clear_cell_output(idx)
            _save_notebook()

        c = state.notebook_cells[idx]
        return {
            "on_run": lambda: page.run_task(_run_cell, c, idx),
            "on_stop": lambda: _stop_cell(idx),
            "on_delete": lambda: _delete_cell(idx),
            "on_move_up": lambda: _move_cell(idx, -1),
            "on_move_down": lambda: _move_cell(idx, 1),
            "on_change": _save_notebook,
            "on_clear_output": _clear,
        }

    def _add_cell(cell_type):
        state.notebook_cells.append(
            {
                "id": str(uuid.uuid4()),
                "type": cell_type,
                "source": "",
                "outputs": [],
                "is_running": False,
            }
        )
        _rebuild_cells()
        _save_notebook()

    def _delete_cell(index):
        if 0 <= index < len(state.notebook_cells):
            state.notebook_cells.pop(index)
            _output_update_ts.pop(index, None)
            _rebuild_cells()
            _save_notebook()

    def _move_cell(index, direction):
        new_index = index + direction
        if 0 <= new_index < len(state.notebook_cells):
            state.notebook_cells[index], state.notebook_cells[new_index] = (
                state.notebook_cells[new_index],
                state.notebook_cells[index],
            )
            _rebuild_cells()
            _save_notebook()

    def _clear_all_outputs(e):
        for i, cell in enumerate(state.notebook_cells):
            cell["outputs"] = []
            _clear_cell_output(i)
        _save_notebook()

    # ── Interactive Stdin Hook ──
    # Track which cell is currently running for stdin routing
    _running_cell_index = {"value": -1}

    def _interactive_stdin_hook(prompt):
        """Handle kernel input requests (input()/getpass()).

        When an xterm terminal is available for the running cell, the user
        types directly in the terminal.  Otherwise falls back to a dialog.
        """
        input_event = threading.Event()
        user_input = {"value": ""}

        prompt_str = str(prompt) if prompt else "Input required"
        is_password = any(
            kw in prompt_str.lower()
            for kw in ("password", "token", "secret", "hf_", "api_key", "getpass")
        )

        # Try terminal-based stdin
        idx = _running_cell_index["value"]
        terminal = None
        if 0 <= idx < len(cell_refs):
            terminal = cell_refs[idx].get("terminal")

        if terminal is not None:
            # Write the prompt to the terminal
            terminal.write(prompt_str.replace("\n", "\r\n"))

            # Buffer user input from terminal keystrokes
            input_buffer = []
            original_on_output = terminal.on_output

            def _terminal_input_handler(e):
                char = e.data if hasattr(e, "data") else str(e)
                if char in ("\r", "\n"):
                    # Enter pressed — submit
                    terminal.write("\r\n")
                    user_input["value"] = "".join(input_buffer)
                    terminal.on_output = original_on_output
                    input_event.set()
                elif char in ("\x7f", "\b"):
                    # Backspace
                    if input_buffer:
                        input_buffer.pop()
                        terminal.write("\b \b")
                else:
                    input_buffer.append(char)
                    if is_password:
                        terminal.write("*")
                    else:
                        terminal.write(char)

            terminal.on_output = _terminal_input_handler

            async def _force_update():
                await asyncio.sleep(0)
                page.update()

            page.run_task(_force_update)
            input_event.wait(timeout=300)
            return user_input["value"]

        # Fallback: dialog-based input
        dialog_field = ft.TextField(
            label=prompt_str,
            autofocus=True,
            password=is_password,
            can_reveal_password=is_password,
        )

        def _submit_input(e):
            user_input["value"] = dialog_field.value or ""
            page.pop_dialog()
            page.update()
            input_event.set()

        dialog_field.on_submit = _submit_input

        dialog = ft.AlertDialog(
            title=ft.Text("Kernel Input Required"),
            content=dialog_field,
            actions=[ft.TextButton("Submit", on_click=_submit_input)],
            modal=True,
        )

        async def _show():
            page.show_dialog(dialog)
            await asyncio.sleep(0)
            page.update()

        page.run_task(_show)
        input_event.wait(timeout=300)
        return user_input["value"]

    # ── Execution Logic ──
    async def _run_cell(cell, index):
        if cell["is_running"]:
            return
        cell["is_running"] = True
        cell["outputs"] = []
        _running_cell_index["value"] = index
        _set_cell_running(index)

        # Write initial text to terminal if it was saved
        if 0 <= index < len(cell_refs):
            terminal = cell_refs[index].get("terminal")
            if terminal is not None and hasattr(terminal, "_initial_text"):
                terminal.write(terminal._initial_text)
                del terminal._initial_text

        def _on_output(text_or_dict):
            if isinstance(text_or_dict, str):
                cell["outputs"].append({"type": "stream", "text": text_or_dict})
            elif isinstance(text_or_dict, dict):
                cell["outputs"].append(text_or_dict)
            page.loop.call_soon_threadsafe(_append_cell_output, index, text_or_dict)

        try:
            await colab_service.exec_code(
                cell["source"],
                session_name,
                timeout=float(state.default_timeout),
                auth_method=state.auth_method,
                on_output=_on_output,
                intercept_oauth=True,
                stdin_hook=_interactive_stdin_hook,
            )
        except Exception as ex:
            err = {"type": "error", "traceback": [str(ex)]}
            cell["outputs"].append(err)
            _append_cell_output(index, err)
        finally:
            cell["is_running"] = False
            _running_cell_index["value"] = -1
            _set_cell_finished(index)
            _save_notebook()
            # Force a final update to flush any remaining output
            await asyncio.sleep(0)
            page.update()

    # Initial Load
    async def _load_notebook():
        loaded_cells = await storage.load_notebook(session_name)
        if loaded_cells:
            state.notebook_cells = loaded_cells
            for c in state.notebook_cells:
                c["is_running"] = False
        else:
            state.notebook_cells = [
                {"type": "code", "source": "", "outputs": [], "is_running": False}
            ]
        _rebuild_cells()

    page.run_task(_load_notebook)

    notebook_section = ft.Container(
        content=cells_list,
        padding=ft.Padding(tokens.SPACE_MD, 0, tokens.SPACE_MD, tokens.SPACE_XL),
    )

    toolbar = build_notebook_toolbar(
        on_add_code=lambda e: _add_cell("code"),
        on_add_markdown=lambda e: _add_cell("markdown"),
        on_clear_all=_clear_all_outputs,
        on_export_ipynb=_on_export_ipynb,
        on_import_ipynb=_on_import_ipynb,
    )

    # ── Full view ─────────────────────────────────────────────────────────────
    def _keep_alive_toggle(label, tooltip, value, on_change):
        return ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Text(
                            label,
                            size=tokens.FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            tooltip,
                            size=tokens.FONT_XXS,
                            color=ft.Colors.with_opacity(
                                0.6, ft.Colors.ON_SURFACE_VARIANT
                            ),
                        ),
                    ],
                    spacing=tokens.SPACE_XXS,
                    expand=True,
                ),
                ft.Switch(
                    value=value,
                    on_change=lambda e: page.run_task(on_change, e),
                    scale=0.75,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    keep_alive_card = glass_card(
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.POWER_SETTINGS_NEW_ROUNDED,
                            size=tokens.ICON_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            "Keep Session Alive",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.ON_SURFACE,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                _keep_alive_toggle(
                    "Active keep-alive",
                    "Ping the session every 60s to prevent timeout",
                    state.keep_alive_enabled,
                    _on_keep_alive,
                ),
                _keep_alive_toggle(
                    "Keep alive on disconnect",
                    "Keep sessions running when the app closes",
                    state.keep_alive_on_disconnect,
                    _on_keep_alive_disconnect,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
        ),
    )

    view_content = ft.Column(
        controls=[
            ft.Stack(
                controls=[
                    ft.Column(
                        controls=[
                            status_header,
                            keep_alive_card,
                            action_row,
                            notebook_section,
                            build_banner_ad(page),
                            ft.Container(height=100),
                        ],
                        spacing=tokens.SPACE_SM,
                        scroll=ft.ScrollMode.AUTO,
                        expand=True,
                    ),
                    ft.Container(
                        content=toolbar,
                        bottom=0,
                        left=0,
                        right=0,
                    ),
                ],
                expand=True,
            ),
        ],
        expand=True,
        spacing=0,
    )

    return ft.View(
        route=f"/session?session={session_name}",
        controls=[view_content],
        padding=0,
        appbar=ft.AppBar(
            leading=ft.Container(
                content=ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    on_click=on_back,
                    icon_size=tokens.ICON_MD,
                    tooltip="Back",
                ),
                padding=ft.Padding(tokens.SPACE_XS, 0, 0, 0),
            ),
            leading_width=48,
            title=ft.Text(
                session_name,
                size=tokens.FONT_LG,
                weight=ft.FontWeight.W_700,
                color=ft.Colors.ON_SURFACE,
            ),
            center_title=True,
            bgcolor=ft.Colors.TRANSPARENT,
            actions=[theme_btn] if theme_btn else [],
        ),
    )
