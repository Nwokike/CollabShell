import json
import os
from pathlib import Path

from services.ipynb_converter import cells_to_ipynb, ipynb_to_cells


async def on_export_ipynb(ctrl, e=None):
    if ctrl.page.platform.is_mobile():
        dl_dir = "/storage/emulated/0/Download"
        if not os.path.exists(dl_dir):
            dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(dl_dir, exist_ok=True)
        path = os.path.join(dl_dir, f"{ctrl.session_name}.ipynb")
    else:
        try:
            path = await ctrl.page.file_picker.save_file(
                allowed_extensions=["ipynb"],
                file_name=f"{ctrl.session_name}.ipynb",
            )
        except ValueError:
            dl_dir = "/storage/emulated/0/Download"
            if not os.path.exists(dl_dir):
                dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(dl_dir, exist_ok=True)
            path = os.path.join(dl_dir, f"{ctrl.session_name}.ipynb")
    if path:
        await on_file_result(ctrl, "export", path=path)


async def on_import_ipynb(ctrl, e=None):
    files = await ctrl.page.file_picker.pick_files(
        allowed_extensions=["ipynb"],
        with_data=bool(getattr(ctrl.page, "web", False)),
    )
    if files:
        await on_file_result(ctrl, "import", files=files)


async def on_file_result(ctrl, op: str, path: str | None = None, files=None):
    if op == "export" and path:
        try:
            ipynb = cells_to_ipynb(ctrl.state.notebook_cells)
            Path(path).write_text(
                json.dumps(ipynb, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if ctrl.snack:
                ctrl.snack("✅ Notebook exported")
        except Exception as ex:
            if ctrl.snack:
                ctrl.snack(f"❌ Export failed: {ex}")

    elif op == "import" and files:
        try:
            picked = files[0]
            if picked.bytes is not None:
                raw = picked.bytes
            else:
                raw = Path(picked.path).read_bytes()
            ipynb = json.loads(raw)
            cells = ipynb_to_cells(ipynb)
            ctrl.state.notebook_cells = cells
            ctrl.rebuild_cells()
            ctrl.save_notebook()
            if ctrl.snack:
                ctrl.snack(f"✅ Imported {len(cells)} cell(s)")
        except Exception as ex:
            if ctrl.snack:
                ctrl.snack(f"❌ Import failed: {ex}")
