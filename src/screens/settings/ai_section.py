"""AI assistant settings — enable, model picker with live rate hints, credits.

The picker is populated from the router's live catalog (active models
only), so a model that is down right now never appears. The rate hint is
shown on each row so users can trade "auto" against a specific model
before they hit a 429.
"""

from __future__ import annotations

import logging

import flet as ft

from core import tokens
from core.styles import glass_card, section_header, tip_text

logger = logging.getLogger("AISection")


def _model_label(model) -> str:
    return f"{model.id}  ·  {model.rate_hint}" if model.rate_hint else model.id


def build_ai_section(page: ft.Page, state, services) -> ft.Column:
    ai = services.ai
    if ai is None:
        return ft.Column()

    async def _on_toggle(e):
        await ai.set_enabled(bool(e.control.value))

    async def _on_model(e):
        await ai.select_model(e.control.value)

    models = ai.models or []
    options = [ft.dropdown.Option(m.id, _model_label(m)) for m in models]

    return ft.Column(
        controls=[
            section_header("AI ASSISTANT"),
            glass_card(
                ft.Column(
                    controls=[
                        # Enable
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.CHAT_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Ask AI",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Powered by Kiri Router — free models, "
                                            "no API key. Every model call uses one "
                                            "of your 50 daily credits."
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Switch(
                                    value=ai.enabled,
                                    on_change=lambda e: page.run_task(_on_toggle, e),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        # Model
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.SMART_TOY_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Model",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Auto lets Kiri pick per question. "
                                            "Pick a model to pin it — the free "
                                            "tier is rate-limited, so auto may "
                                            "retry another model for you."
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Dropdown(
                                    value=ai.selected_model if models else None,
                                    options=options,
                                    hint_text="auto",
                                    width=tokens.INPUT_WIDTH_LG,
                                    text_size=tokens.FONT_SM,
                                    on_select=lambda e: page.run_task(_on_model, e),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        # Credits
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.CONFIRMATION_NUMBER_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            f"{ai.credits_left} credits left today",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "50 per day, one per model call. "
                                            "Calls that fail are refunded."
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.TextButton(
                                    "Clear chat",
                                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                    on_click=lambda e: page.run_task(ai.clear_history),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG,
                    tokens.SPACE_XS,
                    tokens.SPACE_LG,
                    tokens.SPACE_XS,
                ),
            ),
        ],
        spacing=0,
    )


__all__ = ["build_ai_section"]
