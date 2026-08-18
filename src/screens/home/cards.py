"""Reusable card and row visual components for HomeScreen matching SpanInsight."""

from __future__ import annotations

import flet as ft

from core import tokens


def action_button(icon, label: str, on_click, color=None) -> ft.Control:
    """Large interactive action tile for quick session start."""
    active_color = color or ft.Colors.PRIMARY
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, size=tokens.ICON_XL, color=active_color),
                    width=tokens.CARD_ICON_CONTAINER,
                    height=tokens.CARD_ICON_CONTAINER,
                    border_radius=tokens.RADIUS_MD,
                    bgcolor=ft.Colors.with_opacity(0.1, active_color),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Text(
                    label,
                    size=tokens.FONT_XS,
                    text_align=ft.TextAlign.CENTER,
                    weight=ft.FontWeight.W_500,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        ),
        on_click=on_click,
        expand=True,
        ink=True,
        padding=ft.Padding(
            tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD
        ),
        border_radius=tokens.RADIUS_MD,
    )


def feature_card(icon: str, title: str, desc: str, color) -> ft.Container:
    """Card explaining a feature capability of the app."""
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, size=tokens.ICON_LG, color=color),
                    width=tokens.ICON_CONTAINER_SM,
                    height=tokens.ICON_CONTAINER_SM,
                    border_radius=tokens.RADIUS_MD,
                    bgcolor=ft.Colors.with_opacity(tokens.OPACITY_ACCENT, color),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            title,
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(
                            desc,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=3,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=tokens.SPACE_NANO,
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        padding=tokens.SPACE_LG,
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE),
        border=ft.Border.all(
            tokens.DIVIDER_THICKNESS,
            ft.Colors.with_opacity(tokens.OPACITY_CONTAINER, ft.Colors.ON_SURFACE),
        ),
    )


def step_row(number: str, title: str, desc: str) -> ft.Row:
    """Numbered step row for onboarding/how-it-works."""
    return ft.Row(
        controls=[
            ft.Container(
                content=ft.Text(
                    number,
                    size=tokens.FONT_SM,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.WHITE,
                    text_align=ft.TextAlign.CENTER,
                ),
                width=tokens.STEP_BADGE_SIZE,
                height=tokens.STEP_BADGE_SIZE,
                border_radius=tokens.STEP_BADGE_RADIUS,
                bgcolor=ft.Colors.PRIMARY,
                alignment=ft.Alignment.CENTER,
            ),
            ft.Column(
                controls=[
                    ft.Text(
                        title,
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(
                        desc,
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=tokens.SPACE_XXS,
                expand=True,
            ),
        ],
        spacing=tokens.SPACE_MD,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
