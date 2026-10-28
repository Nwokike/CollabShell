import logging

import flet as ft

from core import tokens
from core.theme import AppColors

logger = logging.getLogger("colab")


def make_actions_row(
    on_move_up=None, on_move_down=None, on_delete=None, on_copy=None, on_ask_ai=None
):
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
    if on_ask_ai:
        # Sparkle rather than a word: the row is already four buttons wide and
        # the menu that opens names all three actions in full.
        controls.append(
            ft.IconButton(
                tokens.ASSISTANT_ICON,
                icon_size=tokens.ICON_SM,
                tooltip="Ask AI about this cell",
                on_click=lambda e: on_ask_ai() if on_ask_ai else None,
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


# The three in-cell actions, in the order they are offered. Each entry is the
# action key (what the service dispatches on), its label, its icon, and a line
# of help so the menu explains itself without a tour.
AI_CELL_ACTIONS = (
    (
        "explain",
        "Explain this cell",
        ft.Icons.MENU_BOOK_OUTLINED,
        "What it does and why, in plain language",
    ),
    (
        "fix",
        "Fix the error",
        ft.Icons.BUG_REPORT_OUTLINED,
        "Diagnose the output and write the corrected code",
    ),
    (
        "suggest",
        "Suggest next cell",
        ft.Icons.LIGHTBULB_OUTLINE_ROUNDED,
        "The most useful thing to run next",
    ),
)


def ai_menu(page: ft.Page, cell_id: str, on_pick) -> None:
    """Show the in-cell AI menu.

    `on_pick(action_key)` is awaited by the caller, so it is fire-and-forget
    from here — the menu's job ends at handing off the action.
    """
    rows = []
    for action, label, icon, help_text in AI_CELL_ACTIONS:
        rows.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(icon, size=tokens.ICON_SM),
                        ft.Column(
                            [
                                ft.Text(
                                    label,
                                    size=tokens.FONT_SM,
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Text(
                                    help_text,
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            spacing=0,
                            expand=True,
                            tight=True,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(
                    horizontal=tokens.SPACE_SM, vertical=tokens.SPACE_XS
                ),
                border_radius=tokens.RADIUS_MD,
                ink=True,
                # Bound now: without this every row would close over the last
                # action and all three would Suggest.
                on_click=lambda e, a=action: (page.pop_dialog(), on_pick(a)),
            )
        )
    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(tokens.ASSISTANT_ICON, size=tokens.ICON_SM),
                    ft.Text("Ask AI about this cell"),
                ],
                spacing=tokens.SPACE_SM,
            ),
            content=ft.Container(
                content=ft.Column(rows, spacing=tokens.SPACE_NONE, tight=True),
                width=340,
            ),
            actions=[ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        )
    )


def _snack(page: ft.Page, message: str, is_error: bool = False):
    """Show a floating SnackBar on page."""
    from core.notifications import show_notification

    show_notification(page, message, is_error=is_error)


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
            _snack(page, "📋 Output copied to clipboard!")
        except Exception as ex:
            logger.error("Copy output failed: %s", ex)
    else:
        _snack(page, "No text in output to copy.")
