"""The AI chat panel — a bottom sheet, not a drawer: on a phone the
keyboard rises from the bottom edge and the sheet keeps its own inset
padding so the input stays visible.

The sheet is disposable. The conversation lives in `ai.session`, so
minimizing keeps the reply streaming in the notebook or terminal
underneath — that visibility is the whole point.

Mounting rule (learned the hard way): a `@ft.component` may only be
constructed during another component's render. Event handlers have no
renderer, so `open_ai_panel` never builds the panel — it flips
`ai.sheet_open`, and `AiSheetHost` (rendered once inside AppShell)
constructs the sheet and portals it with Flet's `use_dialog` hook.
"""

from __future__ import annotations

import asyncio

import flet as ft

from ai.credits import COST_PER_TURN
from ai.session import AiSession
from core import tokens
from core.theme import AppColors
from state import ServiceCtx

# How long to wait between model-list attempts while Kiri is cold. Three
# tries covers a busy free tier waking up without leaving the user staring
# at "Starting…" for a minute.
MODEL_RETRY_DELAYS = (1.5, 4.0, 10.0)


@ft.component
def AiPanelContent():
    services = ft.use_context(ServiceCtx)
    ai: AiSession = services.ai
    page = ft.context.page

    # Models are only worth fetching when the sheet is actually open. The
    # retry loop is what makes "Starting Kiri…" resolve on its own: a cold
    # router can take a few seconds, and the user should never have to
    # close and reopen the sheet to get a picker. When the retries run out
    # the state becomes "unreachable" rather than sitting on "Starting…"
    # forever — a label that never resolves is a lie about what is
    # happening.
    async def _load_models():
        for attempt in range(len(MODEL_RETRY_DELAYS)):
            await ai.refresh_models()
            if not ai.models_loading:
                return
            if attempt < len(MODEL_RETRY_DELAYS) - 1:
                await asyncio.sleep(MODEL_RETRY_DELAYS[attempt])
        ai.models_loading = False
        ai.models_unreachable = True
        ai.status = "Can't reach Kiri. Check your connection and reopen."

    ft.on_mounted(lambda: page.run_task(_load_models))

    def _open_chats(e=None):
        from ai.chats_sheet import open_chats_sheet

        open_chats_sheet(page, ai)

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
    for index, m in enumerate(ai.messages):

        def _delete(i=index, ev=None):
            page.run_task(ai.delete_message, i)

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
                    # Long-press deletes one message; the rest keep order.
                    on_long_press=_delete,
                )
            )
        else:
            bubbles.append(
                ft.Container(
                    content=ft.Markdown(
                        m["content"],
                        selectable=True,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                    ),
                    on_long_press=_delete,
                )
            )

    receipt: ft.Control | None = None
    if ai.steps_used:
        receipt = ft.Text(
            f"Assistant used {ai.steps_used} step"
            f"{'s' if ai.steps_used != 1 else ''} · {ai.steps_used * COST_PER_TURN} credits",
            size=tokens.FONT_XXS,
            color=ft.Colors.ON_SURFACE_VARIANT,
            italic=True,
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
    # Step timeline — the user watches every action the Assistant takes, the
    # way DDGS shows each search as its own collapsible group.
    for row in ai.timeline:
        icon, tint = {
            "running": (ft.Icons.PENDING_ROUNDED, ft.Colors.ON_SURFACE_VARIANT),
            "done": (ft.Icons.CHECK_CIRCLE_ROUNDED, AppColors.SUCCESS),
            "denied": (ft.Icons.BLOCK_ROUNDED, AppColors.WARNING),
            "error": (ft.Icons.ERROR_OUTLINE_ROUNDED, AppColors.ERROR),
        }.get(
            row.get("status"), (ft.Icons.CIRCLE_OUTLINED, ft.Colors.ON_SURFACE_VARIANT)
        )
        turn.append(
            ft.Row(
                [
                    ft.Icon(icon, size=tokens.ICON_XS, color=tint),
                    ft.Text(
                        row.get("label", ""),
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        expand=True,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            )
        )
    # Approval card — every confirm-tier action stops here until the user
    # taps Allow or Deny. The reply visibly waits instead of guessing.
    if ai.approval:
        turn.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "The Assistant wants to:",
                            size=tokens.FONT_XS,
                            weight=ft.FontWeight.W_500,
                            color=ft.Colors.ON_SURFACE,
                        ),
                        ft.Text(
                            ai.approval.get("label", ""),
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Row(
                            [
                                ft.FilledButton(
                                    "Allow",
                                    icon=ft.Icons.CHECK_ROUNDED,
                                    on_click=lambda e: ai.resolve_approval(True),
                                ),
                                ft.TextButton(
                                    "Deny",
                                    on_click=lambda e: ai.resolve_approval(False),
                                ),
                            ],
                            spacing=tokens.SPACE_SM,
                        ),
                    ],
                    spacing=tokens.SPACE_XS,
                    tight=True,
                ),
                bgcolor=ft.Colors.with_opacity(0.10, AppColors.WARNING),
                border_radius=tokens.RADIUS_MD,
                padding=ft.Padding(
                    tokens.SPACE_SM, tokens.SPACE_SM, tokens.SPACE_SM, tokens.SPACE_SM
                ),
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
    # the sheet. Three honest states, the same ones the LM Router app
    # distinguishes: a real list, a wait while Kiri starts, and a definite
    # "cannot reach it" — never a neutral empty dropdown that could mean
    # any of them.
    if ai.models:
        options = [ft.DropdownOption(m.id, _model_label(m)) for m in ai.models]
        model_control = ft.Dropdown(
            value=ai.selected_model,
            options=options,
            hint_text="Model",
            width=210,
            menu_height=300,
            enable_filter=True,
            text_size=tokens.FONT_XS,
            on_select=lambda e: page.run_task(ai.select_model, e.control.value),
        )
    else:
        waiting = "Starting Kiri…" if not ai.models_unreachable else "Kiri unreachable"
        model_control = ft.Dropdown(
            value=None,
            options=[ft.DropdownOption("none", waiting)],
            hint_text=waiting,
            width=210,
            disabled=True,
            text_size=tokens.FONT_XS,
        )
    model_row = ft.Row(
        [
            model_control,
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
                        "CollabShell Assistant",
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(
                        ft.Icons.ADD_ROUNDED,
                        tooltip="New chat",
                        icon_size=tokens.ICON_SM,
                        on_click=lambda e: page.run_task(ai.new_chat),
                    ),
                    ft.IconButton(
                        # The list doubles as the delete surface: each chat
                        # has its own delete in there, so this button only
                        # has to mean "my conversations".
                        ft.Icons.FORUM_OUTLINED,
                        tooltip="Chats",
                        icon_size=tokens.ICON_SM,
                        on_click=_open_chats,
                    ),
                    ft.IconButton(
                        # Minimize: hide the sheet, the reply keeps streaming.
                        ft.Icons.VISIBILITY_OFF_OUTLINED,
                        tooltip="Minimize — the reply keeps going",
                        icon_size=tokens.ICON_SM,
                        on_click=lambda e: setattr(ai, "sheet_open", False),
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
                controls=[*([receipt] if receipt else []), *bubbles, *turn],
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


def open_ai_panel(page, ai) -> None:
    """Show the AI sheet. Safe to call from any screen or shortcut — and
    from an event handler, which is exactly where the old version crashed:
    constructing the panel there has no renderer to render it in. This
    only flips a flag; AiSheetHost does the constructing during a render.
    """
    if ai is None:
        return
    ai.sheet_open = True


@ft.component
def AiSheetHost() -> ft.Control:
    """Owns the Assistant sheet, mounted once inside AppShell's tree.

    Everything about this exists because of one Flet 1.0 rule: a component
    function can only run inside a render. The old code built the panel
    inside `show_dialog` calls from button taps — no renderer there — so
    every entry point crashed on a real device. Here the sheet is built
    during THIS component's render (renderer active) and portalled to the
    dialog overlay with `use_dialog`, the same pattern KTV Player uses.
    """
    services = ft.use_context(ServiceCtx)
    ai: AiSession | None = services.ai
    page = ft.context.page

    if ai is not None and ai.sheet_open:
        height = (page.height or 700) * 0.85

        def _dismissed(e=None):
            # The user dragged the sheet away or pressed back: keep the
            # flag true to what is on screen or the next render reopens it.
            ai.sheet_open = False

        sheet = ft.BottomSheet(
            content=ft.Container(
                content=AiPanelContent(),
                height=height,
            ),
            show_drag_handle=True,
            on_dismiss=_dismissed,
            # The body is an expanding ListView: without scrollable=True the
            # sheet ignores the height and stops around mid-screen.
            scrollable=True,
            # Keyboard-aware: the composer rises with the keyboard.
            maintain_bottom_view_insets_padding=True,
        )
        ft.use_dialog(sheet)
    else:
        ft.use_dialog(None)

    return ft.Container(height=0, visible=False)
