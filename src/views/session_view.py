"""Session detail view — full control over an active session."""

from __future__ import annotations

import asyncio
import json
import logging
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

logger = logging.getLogger(__name__)


def build_session_view(
    page: ft.Page,
    colab_service,
    state,
    session_name: str,
    initial_tab: str = "notebook",
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
    # ── Tab Controllers & Terminal Setup ─────────────────────────────────────
    from views.terminal_view import build_terminal_panel

    terminal_panel, terminal_init_func = build_terminal_panel(
        page, session_name, colab_service, snack
    )
    _terminal_initialized = {"value": False}
    tabs_ref = ft.Ref[ft.Tabs]()
    notebook_container_ref = ft.Ref[ft.Container]()
    terminal_container_ref = ft.Ref[ft.Container]()

    def _on_tab_change(e):
        idx = tabs_ref.current.selected_index if tabs_ref.current else 0
        if idx == 1 and not _terminal_initialized["value"]:
            _terminal_initialized["value"] = True
            page.run_task(terminal_init_func)
        page.update()

    def _switch_to_terminal_tab():
        if tabs_ref.current:
            tabs_ref.current.selected_index = 1
            _on_tab_change(None)

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

        def _close_dialog(e=None):
            dialog.open = False
            page.update()

        def _close_and_restart(ev):
            _close_dialog()
            page.run_task(_do_restart)

        dialog = ft.AlertDialog(
            title=ft.Text("Restart Kernel?"),
            content=ft.Text(
                "This will restart the Python kernel. All variables will be lost."
            ),
            actions=[
                ft.TextButton("Cancel", on_click=_close_dialog),
                ft.FilledButton("Restart", on_click=_close_and_restart),
            ],
        )
        page.show_dialog(dialog)

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

        def _close_dialog(e=None):
            dialog.open = False
            page.update()

        def _close_and_stop(ev):
            _close_dialog()
            page.run_task(_do_stop)

        dialog = ft.AlertDialog(
            title=ft.Text("Stop Session?"),
            content=ft.Text(
                "This will terminate the session and release all resources."
            ),
            actions=[
                ft.TextButton("Cancel", on_click=_close_dialog),
                ft.FilledButton("Stop", on_click=_close_and_stop),
            ],
        )
        page.show_dialog(dialog)

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

    def _action_output(prefix: str):
        def _handler(out):
            if not snack:
                return
            msg = out if isinstance(out, str) else out.get("text", "")
            msg = msg.strip()
            if msg:
                line = msg.split("\n")[-1] if "\n" in msg else msg
                page.loop.call_soon_threadsafe(snack, f"{prefix}: {line[:120]}")

        return _handler

    _active_auth_dialog = {"current": None}

    def _close_active_auth():
        if _active_auth_dialog["current"] and _active_auth_dialog["current"].open:
            _active_auth_dialog["current"].open = False
            page.update()

    async def _on_mount_drive(e):
        dialog = ft.AlertDialog(
            title=ft.Text("Mounting Google Drive..."),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.ProgressRing(width=24, height=24, stroke_width=3),
                            ft.Text(
                                "Initiating mount on virtual machine...",
                                size=tokens.FONT_SM,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=tokens.SPACE_MD,
                    ),
                    ft.Text(
                        "Please wait while Colab checks or mounts your Google Drive...",
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                tight=True,
                spacing=tokens.SPACE_SM,
            ),
            actions=[ft.TextButton("Cancel", on_click=lambda e: _close_active_auth())],
            modal=True,
        )
        _active_auth_dialog["current"] = dialog
        page.show_dialog(dialog)
        page.update()

        try:
            await colab_service.mount_drive(
                session_name,
                path=state.drive_mount_path,
                auth_method=state.auth_method,
                on_output=_action_output("Drive"),
                stdin_hook=_interactive_stdin_hook,
            )
            if dialog.open:
                dialog.title = ft.Text("Success")
                dialog.content = ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color="green", size=24),
                        ft.Text(
                            f"Drive mounted at {state.drive_mount_path}",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                )
                dialog.actions = [
                    ft.FilledButton("Done", on_click=lambda e: _close_active_auth())
                ]
                dialog.update()

                async def _auto_close():
                    await asyncio.sleep(1.5)
                    _close_active_auth()

                page.run_task(_auto_close)
        except Exception as ex:
            if dialog.open:
                dialog.title = ft.Text("Failed")
                dialog.content = ft.Row(
                    [
                        ft.Icon(ft.Icons.ERROR_ROUNDED, color="red", size=24),
                        ft.Text(f"Error: {ex}", size=tokens.FONT_SM),
                    ],
                    spacing=tokens.SPACE_SM,
                )
                dialog.actions = [
                    ft.FilledButton("Close", on_click=lambda e: _close_active_auth())
                ]
                dialog.update()

    async def _on_auth_gcp(e):
        dialog = ft.AlertDialog(
            title=ft.Text("Authenticating GCP..."),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.ProgressRing(width=24, height=24, stroke_width=3),
                            ft.Text(
                                "Initiating GCP auth on virtual machine...",
                                size=tokens.FONT_SM,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=tokens.SPACE_MD,
                    ),
                    ft.Text(
                        "Please wait while Colab checks or sets up your credentials...",
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                tight=True,
                spacing=tokens.SPACE_SM,
            ),
            actions=[ft.TextButton("Cancel", on_click=lambda e: _close_active_auth())],
            modal=True,
        )
        _active_auth_dialog["current"] = dialog
        page.show_dialog(dialog)
        page.update()

        try:
            await colab_service.auth_gcp_on_vm(
                session_name,
                auth_method=state.auth_method,
                on_output=_action_output("Auth GCP"),
                stdin_hook=_interactive_stdin_hook,
            )
            if dialog.open:
                dialog.title = ft.Text("Success")
                dialog.content = ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color="green", size=24),
                        ft.Text(
                            "GCP authenticated successfully on VM",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                )
                dialog.actions = [
                    ft.FilledButton("Done", on_click=lambda e: _close_active_auth())
                ]
                dialog.update()

                async def _auto_close():
                    await asyncio.sleep(1.5)
                    _close_active_auth()

                page.run_task(_auto_close)
        except Exception as ex:
            if dialog.open:
                dialog.title = ft.Text("Failed")
                dialog.content = ft.Row(
                    [
                        ft.Icon(ft.Icons.ERROR_ROUNDED, color="red", size=24),
                        ft.Text(f"Error: {ex}", size=tokens.FONT_SM),
                    ],
                    spacing=tokens.SPACE_SM,
                )
                dialog.actions = [
                    ft.FilledButton("Close", on_click=lambda e: _close_active_auth())
                ]
                dialog.update()

    async def _on_view_logs(e):
        if navigate:
            await navigate(f"/history?session={session_name}")

    async def _on_terminal(e):
        """Switch to the real Colab terminal tab."""
        _switch_to_terminal_tab()

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
    # FilePicker results are awaited directly (pick_files/save_file return the
    # selection) rather than via the deprecated on_result callback.
    async def _on_file_result(op: str, path: str = None, files=None):
        if op == "export" and path:
            try:
                ipynb = cells_to_ipynb(state.notebook_cells)
                Path(path).write_text(
                    json.dumps(ipynb, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                if snack:
                    snack("✅ Notebook exported")
            except Exception as ex:
                if snack:
                    snack(f"❌ Export failed: {ex}")

        elif op == "import" and files:
            try:
                picked = files[0]
                # On Android the picker returns file contents (bytes) rather than a
                # filesystem path, so prefer bytes when available.
                if picked.bytes is not None:
                    raw = picked.bytes
                else:
                    raw = Path(picked.path).read_bytes()
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

    async def _on_export_ipynb(e):
        path = await page.file_picker.save_file(
            allowed_extensions=["ipynb"],
            file_name=f"{session_name}.ipynb",
        )
        if path:
            await _on_file_result("export", path=path)

    async def _on_import_ipynb(e):
        files = await page.file_picker.pick_files(
            allowed_extensions=["ipynb"],
            with_data=True,
        )
        if files:
            await _on_file_result("import", files=files)

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
                    constants.LBL_OPEN_BROWSER,
                    lambda e: page.run_task(_on_open_browser, e),
                    AppColors.BADGE_TPU,
                ),
                _action_chip(
                    ft.Icons.TERMINAL_ROUNDED,
                    "Terminal",
                    lambda e: page.run_task(_on_terminal, e),
                    AppColors.BADGE_GPU,
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
    _save_debounce_handle = None

    async def _deferred_update():
        """Yield to the event loop then push the update — fixes mobile rendering."""
        await asyncio.sleep(0)
        page.update()

    def _save_notebook():
        """Immediately persist the notebook.  Used for structural changes
        (add/delete/move cell)."""
        page.run_task(storage.save_notebook, session_name, state.notebook_cells)

    def _debounced_save():
        """Debounce per-keystroke save (1 s) so rapid typing doesn't thrash
        the JSON writer."""
        nonlocal _save_debounce_handle
        if _save_debounce_handle is not None:
            _save_debounce_handle.cancel()
        try:
            loop = asyncio.get_running_loop()
            _save_debounce_handle = loop.call_later(1.0, _save_notebook)
        except RuntimeError:
            _save_notebook()

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
        page.update()

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
        page.update()

    def _append_cell_output(index, text_or_dict):
        if index >= len(cell_refs):
            return
        refs = cell_refs[index]

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

        # Cap text-based output controls to prevent memory exhaustion
        _MAX_OUTPUT_CONTROLS = 5000
        if len(out_col.controls) >= _MAX_OUTPUT_CONTROLS:
            out_col.controls.pop(0)

        out_col.controls.append(
            parse_ansi_to_flet_text(
                raw_text=text, default_size=tokens.FONT_SM, is_error=is_err
            )
        )
        out_col.visible = True
        now = time.monotonic()
        last = _output_update_ts.get(index, 0.0)
        if last == 0.0 or now - last >= 0.15:
            _output_update_ts[index] = now
            page.update()

    def _clear_cell_output(index):
        if index >= len(cell_refs):
            return
        refs = cell_refs[index]
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
            "on_change": _debounced_save,  # per-keystroke → debounced
            "on_clear_output": _clear,
            "on_open_terminal": _switch_to_terminal_tab,
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

    def _interactive_stdin_hook(prompt, *args, **kwargs):
        """Handle kernel input requests (input()/getpass() and Drive OAuth).

        Presents an AlertDialog for clean, non-blocking user input with clickable OAuth links.
        Differentiates between ephemeral Drive mount (no code) vs GCP/standard input (code box required).
        Reuses active authentication dialog if open so the spinner morphs directly into the prompt and back.
        """
        input_event = threading.Event()
        user_input = {"value": ""}

        if isinstance(prompt, dict):
            content_dict = prompt.get("content", {})
            prompt_str = content_dict.get("prompt", str(prompt))
            is_password = content_dict.get("password", False)
        else:
            prompt_str = str(prompt) if prompt else "Input required"
            is_password = any(
                kw in prompt_str.lower()
                for kw in ("password", "token", "secret", "hf_", "api_key", "getpass")
            )

        logger.info(
            f"[stdin_hook] Prompt requested: {prompt_str} (password={is_password})"
        )

        extracted_url = None
        for word in prompt_str.split():
            if word.startswith("http://") or word.startswith("https://"):
                extracted_url = word.strip("'\"),;:")
                break

        is_ephemeral_drive_oauth = bool(
            extracted_url and "authorize-for-drive-credentials-ephem" in extracted_url
        )

        dialog_field = ft.TextField(
            label="Verification Code (Paste code here and click Submit)"
            if extracted_url
            else "Verification Code / Input",
            autofocus=True,
            password=is_password and not bool(extracted_url),
            can_reveal_password=is_password and not bool(extracted_url),
        )

        reused_dialog = bool(
            _active_auth_dialog["current"] and _active_auth_dialog["current"].open
        )
        dialog = (
            _active_auth_dialog["current"]
            if reused_dialog
            else ft.AlertDialog(modal=True)
        )

        def _close_dialog(success=True, message=None):
            if not dialog.open:
                return
            dialog.open = False
            page.update()
            if snack and success and is_ephemeral_drive_oauth:
                snack("✅ Google Drive authorized successfully!")
            elif snack and not success and message:
                snack(f"❌ {message}")

        on_complete = kwargs.get("on_complete")
        if isinstance(on_complete, dict):
            on_complete["fn"] = _close_dialog

        def _submit_input(e=None):
            if not dialog.open:
                return
            user_input["value"] = dialog_field.value or ""
            logger.info("[stdin_hook] User submitted input via dialog")
            if is_ephemeral_drive_oauth:
                dialog.title = ft.Text("Verifying Authorization...")
                dialog.content = ft.Column(
                    [
                        ft.Row(
                            [
                                ft.ProgressRing(width=24, height=24, stroke_width=3),
                                ft.Text(
                                    "Checking credentials with Google servers...",
                                    size=tokens.FONT_SM,
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ],
                            spacing=tokens.SPACE_MD,
                        ),
                        ft.Text(
                            "Please wait up to 20 seconds while Google syncs your authorization across their backend...",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    tight=True,
                    spacing=tokens.SPACE_SM,
                )
                dialog.actions = [
                    ft.TextButton(
                        "Cancel",
                        on_click=lambda e: _close_dialog(
                            False, "Authorization cancelled"
                        ),
                    )
                ]
                dialog.update()
            else:
                if reused_dialog:
                    dialog.title = ft.Text("Verifying Code...")
                    dialog.content = ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.ProgressRing(
                                        width=24, height=24, stroke_width=3
                                    ),
                                    ft.Text(
                                        "Submitting code to virtual machine...",
                                        size=tokens.FONT_SM,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                ],
                                spacing=tokens.SPACE_MD,
                            ),
                            ft.Text(
                                "Please wait while Colab processes your verification code...",
                                size=tokens.FONT_XS,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        tight=True,
                        spacing=tokens.SPACE_SM,
                    )
                    dialog.actions = [
                        ft.TextButton(
                            "Cancel",
                            on_click=lambda e: _close_dialog(
                                False, "Verification cancelled"
                            ),
                        )
                    ]
                    dialog.update()
                else:
                    dialog.open = False
                    page.update()
            input_event.set()

        dialog_field.on_submit = _submit_input

        display_text = prompt_str
        if extracted_url and len(extracted_url) > 60:
            display_text = display_text.replace(extracted_url, "").strip()
            if (
                not display_text
                or "Google Drive Authorization Required" in display_text
            ):
                if is_ephemeral_drive_oauth:
                    display_text = (
                        "Google Drive Authorization Required.\n\n"
                        "1. Click '🌐 Open Link in Browser' below and choose your Google account.\n"
                        "2. Click 'Allow' on the Google permission page.\n\n"
                        "Once the web page says 'Please close this window', return here and click 'Confirm & Continue' below!"
                    )
                else:
                    display_text = (
                        "GCP / Google Cloud Authorization Required.\n\n"
                        "1. Click '🌐 Open Link in Browser' below and sign into your Google account.\n"
                        "2. Click 'Allow' to grant credentials access.\n"
                        "3. Copy the verification code (`4/0AX...`), paste it into the box below, and click 'Submit'!"
                    )

        content_controls = [ft.Text(display_text, size=tokens.FONT_SM, selectable=True)]
        if extracted_url:

            async def _launch_url_task(e=None):
                await ft.UrlLauncher().launch_url(extracted_url)

            async def _copy_url_task(e=None):
                await ft.Clipboard().set(extracted_url)
                if snack:
                    snack("Copied URL to clipboard!")

            content_controls.append(
                ft.Row(
                    [
                        ft.FilledButton(
                            "🌐 Open Link in Browser",
                            on_click=lambda e: page.run_task(_launch_url_task, e),
                        ),
                        ft.IconButton(
                            ft.Icons.COPY_ROUNDED,
                            tooltip="Copy URL",
                            on_click=lambda e: page.run_task(_copy_url_task, e),
                        ),
                    ],
                    wrap=True,
                )
            )
        if not is_ephemeral_drive_oauth:
            content_controls.append(dialog_field)

        dialog.title = ft.Text("Authentication / Input Required")
        dialog.content = ft.Column(
            controls=content_controls, tight=True, spacing=tokens.SPACE_MD
        )
        dialog.actions = [
            ft.TextButton("Cancel", on_click=lambda e: _submit_input()),
            ft.FilledButton(
                "Confirm & Continue" if is_ephemeral_drive_oauth else "Submit",
                on_click=_submit_input,
            ),
        ]

        async def _show():
            if reused_dialog:
                dialog.update()
            else:
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

        def _on_output(text_or_dict):
            # Cap the outputs list at 5000 entries to avoid memory exhaustion
            _MAX_OUTPUT_ENTRIES = 5000
            if isinstance(text_or_dict, str):
                cell["outputs"].append({"type": "stream", "text": text_or_dict})
            elif isinstance(text_or_dict, dict):
                cell["outputs"].append(text_or_dict)
            if len(cell["outputs"]) > _MAX_OUTPUT_ENTRIES:
                cell["outputs"].pop(0)
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
        on_open_terminal=_switch_to_terminal_tab,
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

    notebook_body = ft.Column(
        controls=[
            keep_alive_card,
            action_row,
            notebook_section,
            build_banner_ad(page),
            ft.Container(height=100),
        ],
        spacing=tokens.SPACE_SM,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    notebook_container = ft.Container(
        ref=notebook_container_ref,
        content=ft.Stack(
            controls=[
                notebook_body,
                ft.Container(
                    content=toolbar,
                    bottom=0,
                    left=0,
                    right=0,
                ),
            ],
            expand=True,
        ),
        expand=True,
    )

    terminal_container = ft.Container(
        ref=terminal_container_ref,
        content=terminal_panel,
        expand=True,
    )

    tabs = ft.Tabs(
        ref=tabs_ref,
        length=2,
        selected_index=1 if initial_tab == "terminal" else 0,
        animation_duration=250,
        on_change=_on_tab_change,
        expand=True,
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.TabBar(
                    tabs=[
                        ft.Tab(
                            label="Notebook",
                            icon=ft.Icons.EDIT_NOTE_ROUNDED,
                        ),
                        ft.Tab(
                            label="Real Terminal",
                            icon=ft.Icons.TERMINAL_ROUNDED,
                        ),
                    ]
                ),
                ft.TabBarView(
                    expand=True,
                    controls=[
                        notebook_container,
                        terminal_container,
                    ],
                ),
            ],
        ),
    )

    view_content = ft.Column(
        controls=[
            status_header,
            tabs,
        ],
        expand=True,
        spacing=0,
    )

    if initial_tab == "terminal" and not _terminal_initialized["value"]:
        _terminal_initialized["value"] = True
        page.run_task(terminal_init_func)

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
