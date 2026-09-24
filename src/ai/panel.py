"""The AI chat panel — a bottom sheet, not a drawer: on a phone the
keyboard rises from the bottom edge and the sheet keeps its own inset
padding so the input stays visible.

The sheet is disposable. The conversation lives in `ai.session`, so
minimizing (pop) keeps the reply streaming in the notebook or terminal
underneath — that visibility is the whole point.
"""

from __future__ import annotations

import flet as ft

from ai.session import AiSession
from core import tokens
from core.theme import AppColors
from state import ServiceCtx

# The open sheet, so a second shortcut/FAB tap focuses the existing one
# instead of stacking sheets that pop_dialog would bury under.
_open_sheet: ft.BottomSheet | None = None


@ft.component
def AiPanelContent():
    services = ft.use_context(ServiceCtx)
    ai: AiSession = services.ai
    page = ft.context.page

    # Models are only worth fetching when the sheet is actually open.
    ft.on_mounted(lambda: page.run_task(ai.refresh_models))

    async def _send():
        text = ai.draft
        if not text.strip() or ai.streaming:
            return
        ai.draft = ""
        await ai.send(text)

    def _update(e):
        ai.draft = e.control.value or ""

    # ── Transcript ─────────────────────────────────────────────────────
    bubbles: list[ft.Control] = []
    for m in ai.messages:
        if m["role"] == "user":
            bubbles.append(
                ft.Container(
                    content=ft.Text(
                        m["content"],
                        size=tokens.FONT_SM,
                        color=ft.Colors.WHITE,
                        selectable=True,
                    ),
                    bgcolor=ft.Colors.PRIMARY,
                    border_radius=tokens.RADIUS_MD,
                    padding=ft.Padding(
                        tokens.SPACE_SM,
                        tokens.SPACE_SM,
                        tokens.SPACE_SM,
                        tokens.SPACE_SM,
                    ),
                    align=ft.Alignment.CENTER_RIGHT,
                )
            )
        else:
            bubbles.append(
                ft.Markdown(
                    m["content"],
                    selectable=True,
                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                )
            )

    # ── Current turn ───────────────────────────────────────────────────
    turn: list[ft.Control] = []
    if ai.reasoning:
        label = "Thinking…" if ai.streaming else f"Thought for {ai.reasoning_seconds}s"
        thinking: list[ft.Control] = [
            ft.Row(
                [
                    ft.Icon(
                        ft.Icons.PSYCHOLOGY_ROUNDED,
                        size=tokens.ICON_XS,
                        color=AppColors.WARNING if ai.streaming else AppColors.SUCCESS,
                    ),
                    ft.Text(
                        label,
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        weight=ft.FontWeight.W_500,
                    ),
                    ft.Container(expand=True),
                    ft.Icon(
                        ft.Icons.EXPAND_LESS_ROUNDED
                        if ai.reasoning_open
                        else ft.Icons.EXPAND_MORE_ROUNDED,
                        size=tokens.ICON_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=tokens.SPACE_XS,
            )
        ]
        if ai.reasoning_open:
            thinking.append(
                ft.Text(
                    ai.reasoning,
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    selectable=True,
                )
            )
        turn.append(
            ft.Container(
                content=ft.Column(thinking, spacing=tokens.SPACE_XS, tight=True),
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
                border_radius=tokens.RADIUS_SM,
                padding=ft.Padding(
                    tokens.SPACE_SM, tokens.SPACE_SM, tokens.SPACE_SM, tokens.SPACE_SM
                ),
                ink=True,
                on_click=lambda e: setattr(ai, "reasoning_open", not ai.reasoning_open),
            )
        )
    if ai.answer:
        turn.append(
            ft.Markdown(
                ai.answer,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            )
        )
    if ai.streaming and not ai.answer and not ai.reasoning:
        turn.append(
            ft.Row(
                [
                    ft.ProgressRing(width=14, height=14, stroke_width=2),
                    ft.Text(
                        "Thinking…",
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            )
        )
    if ai.answered_by and ai.answered_by != ai.selected_model and not ai.streaming:
        turn.append(
            ft.Text(
                f"answered by {ai.answered_by}",
                size=tokens.FONT_XXS,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            )
        )
    if ai.error:
        turn.append(
            ft.Text(
                ai.error,
                size=tokens.FONT_XS,
                color=AppColors.ERROR,
            )
        )
    if ai.status and not ai.error:
        turn.append(
            ft.Text(
                ai.status,
                size=tokens.FONT_XS,
                color=AppColors.WARNING,
            )
        )

    # ── Model picker ───────────────────────────────────────────────────
    # DropdownOption (not dropdown.Option) is the 1.0 name, and menu_height
    # is what makes the ~48-entry catalog scrollable instead of overflowing
    # the sheet.
    options = [ft.DropdownOption(m.id, _model_label(m)) for m in ai.models]
    model_row = ft.Row(
        [
            ft.Dropdown(
                value=ai.selected_model if ai.models else None,
                options=options,
                hint_text="Model",
                width=210,
                menu_height=300,
                text_size=tokens.FONT_XS,
                on_select=lambda e: page.run_task(ai.select_model, e.control.value),
            ),
            ft.Text(
                f"{ai.credits_left} credits left today",
                size=tokens.FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        ],
        spacing=tokens.SPACE_SM,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    return ft.Column(
        [
            # Header
            ft.Row(
                [
                    ft.Icon(
                        ft.Icons.CHAT_ROUNDED,
                        color=ft.Colors.PRIMARY,
                        size=tokens.ICON_MD,
                    ),
                    ft.Text(
                        "CollabShell AI",
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.W_BOLD,
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE_ROUNDED,
                        tooltip="Clear chat",
                        icon_size=tokens.ICON_SM,
                        on_click=lambda e: page.run_task(ai.clear_history),
                    ),
                    ft.IconButton(
                        # Minimize: pop the sheet, the reply keeps streaming.
                        ft.Icons.VISIBILITY_OFF_OUTLINED,
                        tooltip="Minimize — the reply keeps going",
                        icon_size=tokens.ICON_SM,
                        on_click=lambda e: page.pop_dialog(),
                    ),
                ],
                spacing=tokens.SPACE_XS,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Divider(
                height=1, color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
            ),
            # Transcript — auto_scroll pins to the newest token and
            # suspends itself the moment the user scrolls up to read.
            ft.ListView(
                controls=[*bubbles, *turn],
                auto_scroll=True,
                auto_scroll_animation=0,
                spacing=tokens.SPACE_SM,
                padding=tokens.SPACE_XS,
                expand=True,
            ),
            ft.Divider(
                height=1, color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
            ),
            model_row,
            # Composer
            ft.Row(
                [
                    ft.TextField(
                        value=ai.draft,
                        hint_text="Ask anything about your code or Colab…",
                        multiline=True,
                        shift_enter=True,
                        min_lines=1,
                        max_lines=4,
                        text_size=tokens.FONT_SM,
                        border_radius=tokens.RADIUS_MD,
                        on_change=_update,
                        # Enter sends; Shift+Enter makes a newline.
                        on_submit=lambda e: page.run_task(_send),
                    ),
                    ft.IconButton(
                        ft.Icons.STOP_ROUNDED
                        if ai.streaming
                        else ft.Icons.SEND_ROUNDED,
                        icon_color=AppColors.ERROR
                        if ai.streaming
                        else ft.Colors.PRIMARY,
                        tooltip="Stop" if ai.streaming else "Send",
                        on_click=(lambda e: ai.stop())
                        if ai.streaming
                        else (lambda e: page.run_task(_send)),
                    ),
                ],
                spacing=tokens.SPACE_XS,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=tokens.SPACE_SM,
        expand=True,
    )


def _model_label(model) -> str:
    label = model.id
    if model.rate_hint:
        label = f"{label}  ·  {model.rate_hint}"
    return label


def open_ai_panel(page, services) -> None:
    """Show the AI sheet. Safe to call from any screen or shortcut."""
    global _open_sheet
    if services.ai is None:
        return
    if _open_sheet is not None and _open_sheet.open:
        return  # already showing — never stack sheets
    height = (page.height or 700) * 0.85
    _open_sheet = ft.BottomSheet(
        content=ft.Container(
            content=AiPanelContent(),
            height=height,
        ),
        show_drag_handle=True,
        # The body is an expanding ListView: without scrollable=True the
        # sheet ignores the height and stops around mid-screen.
        scrollable=True,
        # Keyboard-aware: the composer rises with the keyboard.
        maintain_bottom_view_insets_padding=True,
    )
    page.show_dialog(_open_sheet)
