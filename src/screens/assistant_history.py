"""Assistant conversation history — switch or delete saved chats.

Reads through `conversation_service`, so what is shown is exactly what save/
load round-trips: newest first, title from the first user message, message
count and age. Deleting tombstones the chat for 60 seconds, which is what stops
a save already in flight from rewriting the file after the user deletes it.

Switching chats goes straight to `open_assistant`: the session is retained on
the page, so replacing its transcript restores the same view rather than
stacking another one.
"""

from __future__ import annotations

import logging

import flet as ft

from core import tokens
from core.notifications import show_notification
from services import conversation_service as conversations

logger = logging.getLogger("assistant_history")


def show_history_dialog(page: ft.Page, state, services, rows: list[dict]) -> None:
    """Show the saved chats. ``rows`` comes from conversation_service."""
    from screens.assistant_view import ChatSession

    def _close():
        page.pop_dialog()

    def _delete(cid: str):
        conversations.delete_conversation(cid)
        remaining = [r for r in rows if r.get("id") != cid]
        rows[:] = remaining
        _rerender()
        show_notification(page, "Chat deleted.")

    def _open(cid: str):
        # Load before closing so a failed read cannot leave the chat closed.
        payload = conversations.load_conversation(cid)
        if payload is None:
            show_notification(page, "Could not open that chat.", is_error=True)
            return
        _close()
        session = getattr(page, "_assistant_session", None)
        if isinstance(session, ChatSession):
            if session.load_conversation(cid) and session.view not in page.views:
                # The chat was minimized: swapping in the new transcript without
                # re-showing it would leave the user looking at nothing.
                session.restore()
            return
        _open_fresh(cid)

    def _open_fresh(cid: str):
        from screens.assistant_view import open_assistant

        state.active_assistant_conversation = cid
        open_assistant(page, state, services)

    list_column = ft.Column(
        spacing=tokens.SPACE_XS,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    def _rerender():
        controls = []
        if not rows:
            controls.append(
                ft.Container(
                    content=ft.Text(
                        "No saved chats yet.",
                        size=tokens.FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    padding=ft.Padding.all(tokens.SPACE_LG),
                    alignment=ft.Alignment.CENTER,
                )
            )
        for row in rows:
            cid = row.get("id", "")
            controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        str(row.get("title") or "New chat"),
                                        size=tokens.FONT_SM,
                                        weight=ft.FontWeight.W_600,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Text(
                                        conversations.summarize(row),
                                        size=tokens.FONT_XS,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                ],
                                spacing=0,
                                expand=True,
                                tight=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                icon_size=tokens.ICON_SM,
                                tooltip="Delete",
                                on_click=lambda e, cid=cid: _delete(cid),
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
                    on_click=lambda e, cid=cid: _open(cid),
                )
            )
        list_column.controls = controls
        try:
            list_column.update()
        except Exception:
            logger.debug("history rerender failed")

    _rerender()

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Text("Assistant chats"),
            content=ft.Container(content=list_column, width=420, height=340),
            actions=[
                ft.TextButton("Close", on_click=lambda e: _close()),
                ft.TextButton(
                    "New chat",
                    on_click=lambda e: (_close(), _open_fresh(conversations.new_conversation_id())),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
    )
