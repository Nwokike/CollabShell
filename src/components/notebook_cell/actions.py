import flet as ft
from core import tokens
from core.theme import AppColors


def make_actions_row(on_move_up, on_move_down, on_delete):
    return ft.Row(
        controls=[
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
        ],
        spacing=0,
    )


async def copy_output(page: ft.Page, outputs: list):
    text_to_copy = ""
    for out in outputs:
        if out.get("type") == "stream":
            text_to_copy += out.get("text", "") + "\n"
        elif out.get("type") == "error":
            text_to_copy += "\n".join(out.get("traceback", [])) + "\n"
        elif out.get("type") in ["execute_result", "display_data"]:
            data = out.get("data", {})
            if "text/plain" in data:
                text_to_copy += data["text/plain"] + "\n"
    if text_to_copy:
        await ft.Clipboard().set(text_to_copy.strip())
        page.show_dialog(ft.SnackBar(ft.Text("Output copied to clipboard!")))
