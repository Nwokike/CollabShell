import asyncio
import time
import uuid
import logging
import flet as ft
from core import tokens
from components.notebook_cell import build_notebook_cell

logger = logging.getLogger("session_controller")


class SessionController:
    def __init__(
        self,
        page: ft.Page,
        colab_service,
        state,
        session_name: str,
        storage,
        snack,
        navigate,
        on_back,
        cells_list,
    ):
        self.page = page
        self.colab_service = colab_service
        self.state = state
        self.session_name = session_name
        self.storage = storage
        self.snack = snack
        self.navigate = navigate
        self.on_back = on_back

        self.cells_list = cells_list
        self.cell_refs = []  # List of Ref dicts
        self.output_update_ts = {}
        self.save_debounce_handle = None
        self.rebuild_throttle = 0.0
        self.running_cell_index = -1
        self.terminal_container_ref = None
        self.notebook_container_ref = None
        self.tabs_ref = None

    async def deferred_update(self):
        await asyncio.sleep(0)
        self.page.update()

    def save_notebook(self):
        try:
            if getattr(self.page, "_session", getattr(self.page, "session", None)):
                self.page.run_task(
                    self.storage.save_notebook,
                    self.session_name,
                    self.state.notebook_cells,
                )
        except RuntimeError:
            pass

    def debounced_save(self):
        if self.save_debounce_handle is not None:
            self.save_debounce_handle.cancel()
        try:
            loop = asyncio.get_running_loop()
            self.save_debounce_handle = loop.call_later(1.0, self.save_notebook)
        except RuntimeError:
            self.save_notebook()

    def set_cell_running(self, index):
        if index >= len(self.cell_refs):
            return
        refs = self.cell_refs[index]
        play = refs["play_btn"].current
        stop = refs["stop_row"].current
        if play:
            play.visible = False
        if stop:
            stop.visible = True
        out = refs["output"].current
        out_panel = refs.get("output_panel", ft.Ref()).current
        if out:
            out.visible = True
            if not out.height:
                out.height = 40
        if out_panel:
            out_panel.visible = True
        self.page.update()

    def set_cell_finished(self, index):
        if index >= len(self.cell_refs):
            return
        refs = self.cell_refs[index]
        play = refs["play_btn"].current
        stop = refs["stop_row"].current
        if play:
            play.visible = True
        if stop:
            stop.visible = False
        self.page.update()

    def append_cell_output(self, index, text_or_dict):
        if index >= len(self.cell_refs):
            return
        refs = self.cell_refs[index]
        out_col = refs["output"].current
        out_panel = refs.get("output_panel", ft.Ref()).current
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

        _MAX_OUTPUT_CONTROLS = 5000
        if len(out_col.controls) >= _MAX_OUTPUT_CONTROLS:
            out_col.controls.pop(0)

        out_col.controls.append(
            parse_ansi_to_flet_text(
                raw_text=text, default_size=tokens.FONT_SM, is_error=is_err
            )
        )
        out_col.visible = True
        if out_panel:
            out_panel.visible = True

        # Calculate dynamic line count & expand height from 40px up to 220px
        total_lines = 0
        for ctrl in out_col.controls:
            txt = getattr(ctrl, "value", "") or ""
            total_lines += max(txt.count("\n") + 1, 1)

        out_col.height = min(max(total_lines * 20 + 16, 40), 220)

        now = time.monotonic()
        last = self.output_update_ts.get(index, 0.0)
        if last == 0.0 or now - last >= 0.15:
            self.output_update_ts[index] = now
            self.page.update()

    def clear_cell_output(self, index):
        if index >= len(self.cell_refs):
            return
        refs = self.cell_refs[index]
        out_col = refs["output"].current
        out_panel = refs.get("output_panel", ft.Ref()).current
        if out_col:
            out_col.controls.clear()
            out_col.visible = False
        if out_panel:
            out_panel.visible = False
        self.page.run_task(self.deferred_update)

    def rebuild_cells(self, force=False):
        now = time.monotonic()
        if not force and now - self.rebuild_throttle < 0.15:
            return
        self.rebuild_throttle = now
        self.cell_refs.clear()
        self.cells_list.controls.clear()
        for i, cell in enumerate(self.state.notebook_cells):
            container, refs = build_notebook_cell(
                self.page, cell, **self.make_callbacks(i)
            )
            self.cells_list.controls.append(container)
            self.cell_refs.append(refs)
            if (i + 1) % 3 == 0:
                from core.styles import build_banner_ad

                self.cells_list.controls.append(build_banner_ad(self.page))
        self.page.run_task(self.deferred_update)

    def stop_cell(self, idx):
        if 0 <= idx < len(self.state.notebook_cells):
            self.colab_service.cancel()
            cell = self.state.notebook_cells[idx]
            cell["outputs"].append(
                {"type": "error", "traceback": ["Execution cancelled by user"]}
            )
            cell["is_running"] = False
            self.append_cell_output(
                idx, {"type": "error", "traceback": ["Execution cancelled by user"]}
            )
            self.set_cell_finished(idx)
            self.save_notebook()

    def switch_to_terminal_tab(self):
        if self.tabs_ref and self.tabs_ref.current:
            self.tabs_ref.current.selected_index = 1
        if self.notebook_container_ref and self.notebook_container_ref.current:
            self.notebook_container_ref.current.visible = False
        if self.terminal_container_ref and self.terminal_container_ref.current:
            self.terminal_container_ref.current.visible = True
        self.page.update()

    def make_callbacks(self, idx):
        def _clear():
            self.state.notebook_cells[idx]["outputs"] = []
            self.clear_cell_output(idx)
            self.save_notebook()

        c = self.state.notebook_cells[idx]
        return {
            "on_run": lambda: self.page.run_task(self.run_cell, c, idx),
            "on_stop": lambda: self.stop_cell(idx),
            "on_delete": lambda: self.delete_cell(idx),
            "on_move_up": lambda: self.move_cell(idx, -1),
            "on_move_down": lambda: self.move_cell(idx, 1),
            "on_change": self.debounced_save,
            "on_clear_output": _clear,
            "on_open_terminal": self.switch_to_terminal_tab,
        }

    def add_cell(self, cell_type):
        self.state.notebook_cells.append(
            {
                "id": str(uuid.uuid4()),
                "type": cell_type,
                "source": "",
                "outputs": [],
                "is_running": False,
            }
        )
        self.rebuild_cells()
        self.save_notebook()

    def delete_cell(self, index):
        if 0 <= index < len(self.state.notebook_cells):
            self.state.notebook_cells.pop(index)
            self.output_update_ts.pop(index, None)
            self.rebuild_cells()
            self.save_notebook()

    def move_cell(self, index, direction):
        new_index = index + direction
        if 0 <= new_index < len(self.state.notebook_cells):
            self.state.notebook_cells[index], self.state.notebook_cells[new_index] = (
                self.state.notebook_cells[new_index],
                self.state.notebook_cells[index],
            )
            self.rebuild_cells()
            self.save_notebook()

    def clear_all_outputs(self, e):
        for i, cell in enumerate(self.state.notebook_cells):
            cell["outputs"] = []
            self.clear_cell_output(i)
        self.save_notebook()

    async def run_cell(self, cell, index):
        if cell["is_running"]:
            return
        cell["is_running"] = True
        cell["outputs"] = []
        self.running_cell_index = index
        self.set_cell_running(index)

        def _on_output(text_or_dict):
            _MAX_OUTPUT_ENTRIES = 5000
            if isinstance(text_or_dict, str):
                cell["outputs"].append({"type": "stream", "text": text_or_dict})
            elif isinstance(text_or_dict, dict):
                cell["outputs"].append(text_or_dict)
            if len(cell["outputs"]) > _MAX_OUTPUT_ENTRIES:
                cell["outputs"].pop(0)
            self.page.loop.call_soon_threadsafe(
                self.append_cell_output, index, text_or_dict
            )

        try:
            await self.colab_service.exec_code(
                cell["source"],
                self.session_name,
                timeout=float(self.state.default_timeout),
                auth_method=self.state.auth_method,
                on_output=_on_output,
                intercept_oauth=True,
                stdin_hook=self.interactive_stdin_hook,
            )
        except Exception as ex:
            err = {"type": "error", "traceback": [str(ex)]}
            cell["outputs"].append(err)
            self.append_cell_output(index, err)
        finally:
            cell["is_running"] = False
            self.running_cell_index = -1
            self.set_cell_finished(index)
            self.save_notebook()
            await asyncio.sleep(0)
            self.page.update()

    async def load_notebook(self):
        loaded_cells = await self.storage.load_notebook(self.session_name)
        if loaded_cells:
            self.state.notebook_cells = loaded_cells
            for c in self.state.notebook_cells:
                c["is_running"] = False
        else:
            self.state.notebook_cells = [
                {"type": "code", "source": "", "outputs": [], "is_running": False}
            ]
        self.rebuild_cells()

    def interactive_stdin_hook(self, prompt, *args, **kwargs):
        from views.session.dialogs import show_interactive_stdin_dialog

        return show_interactive_stdin_dialog(self, prompt, *args, **kwargs)
