import logging

import flet as ft

from core import tokens
from core.theme import AppColors

logger = logging.getLogger("colab")


def make_actions_row(
    on_move_up=None,
    on_move_down=None,
    on_delete=None,
    on_copy=None,
    copy_data: str | None = None,
    on_ask_ai=None,
):
    controls = []
    if on_ask_ai:
        # The chat icon is the Assistant's entry point everywhere — the FAB,
        # the shortcut, and every cell. Same icon, same meaning.
        controls.append(
            ft.IconButton(
                ft.Icons.CHAT_ROUNDED,
                icon_size=tokens.ICON_SM,
                icon_color=ft.Colors.PRIMARY,
                tooltip="Ask the Assistant about this cell",
                on_click=lambda e: on_ask_ai(),
            )
        )
    if on_copy:
        copy_value = (copy_data or "").strip()
        controls.append(
            ft.IconButton(
                ft.Icons.COPY_ROUNDED,
                icon_size=tokens.ICON_SM,
                tooltip="Copy Code",
                action=ft.CopyToClipboard(data=copy_value) if copy_value else None,
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


def _snack(page: ft.Page, message: str, is_error: bool = False):
    """Show a floating SnackBar on page."""
    from core.notifications import show_notification

    show_notification(page, message, is_error=is_error)


def outputs_to_text(outputs: list) -> str:
    """Flatten any output shape (stream, error, result) into plain text.

    Shared with the Assistant so the cell sheet and "fix this error" show
    exactly what the user sees, rather than a second, drifting parser.
    """
    parts: list[str] = []
    for out in outputs or []:
        if isinstance(out, str):
            parts.append(out)
            continue
        if not isinstance(out, dict):
            continue

        out_type = out.get("type") or out.get("output_type")
        if out_type == "stream":
            txt = out.get("text", "")
            if isinstance(txt, list):
                txt = "".join(txt)
            parts.append(str(txt))
        elif out_type == "error":
            tb = out.get("traceback", [])
            tb_str = "\n".join(tb) if isinstance(tb, list) else str(tb)
            ename, evalue = out.get("ename", ""), out.get("evalue", "")
            head = f"{ename}: {evalue}" if ename or evalue else ""
            parts.append("\n".join(x for x in (head, tb_str) if x))
        elif out_type in ("execute_result", "display_data"):
            data = out.get("data", {})
            if "text/plain" in data:
                txt = data["text/plain"]
                if isinstance(txt, list):
                    txt = "".join(txt)
                parts.append(str(txt))
        elif "text" in out:
            txt = out["text"]
            if isinstance(txt, list):
                txt = "".join(txt)
            parts.append(str(txt))
    return "\n".join(p for p in parts if p).strip()


def has_error(outputs: list) -> bool:
    """True when the cell ended in an error worth offering to fix."""
    return any(
        isinstance(o, dict) and (o.get("type") or o.get("output_type")) == "error"
        for o in (outputs or [])
    )


def error_to_text(outputs: list) -> str:
    """Just the failing part — the traceback, without the noisy prints."""
    return outputs_to_text([o for o in (outputs or []) if _is_error(o)])


def _is_error(out) -> bool:
    return (
        isinstance(out, dict) and (out.get("type") or out.get("output_type")) == "error"
    )


async def copy_code(page: ft.Page, code: str):
    """Copy cell source code to clipboard."""
    if not code or not code.strip():
        _snack(page, "Cell code is empty.")
        return
    try:
        await ft.Clipboard().set(code.strip())
        _snack(page, "📋 Cell code copied to clipboard!")
    except Exception as ex:
        logger.error("Copy code failed: %s", ex)


async def copy_output(page: ft.Page, outputs: list):
    """Copy notebook output text to clipboard supporting all output types."""
    if not outputs:
        _snack(page, "No output to copy.")
        return

    import re

    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    final_text = ansi_escape.sub("", outputs_to_text(outputs)).strip()

    if final_text:
        try:
            await ft.Clipboard().set(final_text)
            _snack(page, "📋 Output copied to clipboard!")
        except Exception as ex:
            logger.error("Copy output failed: %s", ex)
    else:
        _snack(page, "No text in output to copy.")
