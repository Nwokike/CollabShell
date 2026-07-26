import logging

import flet as ft

from core import tokens
from core.theme import AppColors

logger = logging.getLogger("colab")


def make_actions_row(on_move_up=None, on_move_down=None, on_delete=None, on_copy=None):
    controls = []
    if on_copy:
        controls.append(
            ft.IconButton(
                ft.Icons.COPY_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Copy Code",
                on_click=lambda e: on_copy() if on_copy else None,
            )
        )
    controls.extend(
        [
            ft.IconButton(
                ft.Icons.ARROW_UPWARD_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Move Up",
                on_click=lambda e: on_move_up() if on_move_up else None,
            ),
            ft.IconButton(
                ft.Icons.ARROW_DOWNWARD_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Move Down",
                on_click=lambda e: on_move_down() if on_move_down else None,
            ),
            ft.IconButton(
                ft.Icons.DELETE_OUTLINE_ROUNDED,
                icon_size=tokens.ICON_SM,
                icon_color=AppColors.ERROR,
                tooltip="Delete Cell",
                on_click=lambda e: on_delete() if on_delete else None,
            ),
        ]
    )
    return ft.Row(controls=controls, spacing=0)


async def copy_code(page: ft.Page, code: str):
    """Copy cell source code to clipboard."""
    if not code or not code.strip():
        page.show_dialog(ft.SnackBar(ft.Text("Cell code is empty.")))
        return
    try:
        await ft.Clipboard().set(code.strip())
        page.show_dialog(ft.SnackBar(ft.Text("Cell code copied to clipboard!")))
    except Exception as ex:
        logger.error("Copy code failed: %s", ex)


async def copy_output(page: ft.Page, outputs: list):
    """Copy notebook output text to clipboard supporting all output types."""
    if not outputs:
        page.show_dialog(ft.SnackBar(ft.Text("No output to copy.")))
        return

    text_to_copy = ""
    for out in outputs:
        if isinstance(out, str):
            text_to_copy += out + "\n"
            continue
        if not isinstance(out, dict):
            continue

        out_type = out.get("type") or out.get("output_type")
        if out_type == "stream":
            txt = out.get("text", "")
            if isinstance(txt, list):
                txt = "".join(txt)
            text_to_copy += str(txt) + "\n"
        elif out_type == "error":
            tb = out.get("traceback", [])
            if isinstance(tb, list):
                tb_str = "\n".join(tb)
            else:
                tb_str = str(tb)
            ename = out.get("ename", "")
            evalue = out.get("evalue", "")
            if ename or evalue:
                text_to_copy += f"{ename}: {evalue}\n"
            text_to_copy += tb_str + "\n"
        elif out_type in ["execute_result", "display_data"]:
            data = out.get("data", {})
            if "text/plain" in data:
                txt = data["text/plain"]
                if isinstance(txt, list):
                    txt = "".join(txt)
                text_to_copy += str(txt) + "\n"
        elif "text" in out:
            txt = out["text"]
            if isinstance(txt, list):
                txt = "".join(txt)
            text_to_copy += str(txt) + "\n"

    import re

    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    final_text = ansi_escape.sub("", text_to_copy).strip()

    if final_text:
        try:
            await ft.Clipboard().set(final_text)
            page.show_dialog(ft.SnackBar(ft.Text("Output copied to clipboard!")))
        except Exception as ex:
            logger.error("Copy output failed: %s", ex)
    else:
        page.show_dialog(ft.SnackBar(ft.Text("No text in output to copy.")))
