"""The chat list — every conversation the user has, each deletable.

The Assistant is one conversation at a time, but not one conversation
ever. This sheet is where a user switches threads, starts a new one, or
throws away the one that went nowhere. Deleting asks first, because the
alternative is a mis-tap erasing a long transcript.
"""

from __future__ import annotations

import time

import flet as ft

from core import tokens
from core.theme import AppColors


def _when(ts: float) -> str:
    """Relative time beats a date here: '5m ago' is what a phone chat list
    shows and it is what the user is actually comparing against."""
    seconds = max(time.time() - float(ts or 0), 0)
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    if seconds < 604800:
        return f"{int(seconds // 86400)}d ago"
    return time.strftime("%d %b", time.localtime(ts))


def open_chats_sheet(page, ai) -> None:
    """List the chats, newest first."""
    if ai is None:
        return

    def _confirm_delete(chat_id: str, title: str, e=None):
        page.pop_dialog()
        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Delete this chat?"),
                content=ft.Text(
                    f"“{title or 'New chat'}” and everything in it will be gone."
                ),
                actions=[
                    ft.TextButton("Keep", on_click=lambda ev: page.pop_dialog()),
                    ft.FilledButton(
                        "Delete",
                        color=AppColors.ERROR,
                        on_click=lambda ev: (
                            page.pop_dialog(),
                            page.run_task(ai.delete_chat, chat_id),
                        ),
                    ),
                ],
            )
        )

    rows: list[ft.Control] = [
        ft.ListTile(
            leading=ft.Icon(ft.Icons.ADD_ROUNDED, color=ft.Colors.PRIMARY),
            title=ft.Text("New chat", weight=ft.FontWeight.W_500),
            subtitle=ft.Text("Start a fresh conversation"),
            on_click=lambda e: (
                page.pop_dialog(),
                page.run_task(ai.new_chat),
            ),
        ),
    ]

    if not ai.chats:
        rows.append(
            ft.Padding(
                content=ft.Text(
                    "No saved chats yet.",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                padding=tokens.SPACE_MD,
            )
        )

    for chat in ai.chats:
        is_active = chat["id"] == ai.active_chat_id
        title = chat.get("title") or "New chat"
        count = len(chat.get("messages") or [])
        rows.append(
            ft.ListTile(
                leading=ft.Icon(
                    ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
                    color=ft.Colors.PRIMARY if is_active else None,
                ),
                title=ft.Text(
                    title,
                    weight=ft.FontWeight.W_600 if is_active else None,
                ),
                subtitle=ft.Text(
                    _when(chat.get("updated") or 0)
                    + (f" · {count} messages" if count else ""),
                    size=tokens.FONT_XS,
                ),
                bgcolor=(
                    ft.Colors.with_opacity(0.10, ft.Colors.PRIMARY)
                    if is_active
                    else None
                ),
                on_click=lambda e, cid=chat["id"]: (
                    page.pop_dialog(),
                    page.run_task(ai.switch_chat, cid),
                ),
                trailing=ft.IconButton(
                    ft.Icons.DELETE_OUTLINE_ROUNDED,
                    icon_size=tokens.ICON_SM,
                    icon_color=AppColors.ERROR,
                    tooltip="Delete this chat",
                    on_click=lambda e, cid=chat["id"], t=title: _confirm_delete(
                        cid, t, e
                    ),
                ),
            )
        )

    page.show_dialog(
        ft.BottomSheet(
            content=ft.Container(
                content=ft.Column(controls=rows, spacing=0, tight=True),
                padding=ft.Padding(
                    tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD
                ),
                height=min(len(rows) * 72 + 40, (page.height or 700) * 0.7),
            ),
            show_drag_handle=True,
        )
    )


__all__ = ["open_chats_sheet"]
