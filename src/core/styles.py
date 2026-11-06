"""Reusable widget factories."""

import logging

import flet as ft

from core import tokens

logger = logging.getLogger(__name__)


def section_header(text: str) -> ft.Container:
    return ft.Container(
        content=ft.Text(
            text,
            size=tokens.FONT_SM,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.PRIMARY,
            style=ft.TextStyle(letter_spacing=1),
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_XS,
        ),
    )


def setting_tile(
    icon: ft.Icons = None,
    title: str = "",
    subtitle: str = "",
    on_click=None,
) -> ft.Container:
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(
                    icon,
                    size=tokens.ICON_LG,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
                if icon
                else ft.Container(width=0),
                ft.Column(
                    controls=[
                        ft.Text(
                            title,
                            size=tokens.FONT_MD,
                            weight=ft.FontWeight.W_500,
                        ),
                        ft.Text(
                            subtitle,
                            size=tokens.FONT_XS,
                            color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                        ),
                    ],
                    spacing=tokens.SPACE_XXS,
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_LG,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=14,
            bottom=14,
        ),
        on_click=on_click,
    )


def glass_card(content: ft.Control, **kwargs) -> ft.Container:
    from core.theme import adaptive_glass_bg, adaptive_glass_border

    return ft.Container(
        content=content,
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_MD,
        ),
        border_radius=tokens.RADIUS_LG,
        bgcolor=adaptive_glass_bg(),
        border=ft.Border.all(width=1, color=adaptive_glass_border()),
        **kwargs,
    )


def solid_card(content: ft.Control, **kwargs) -> ft.Container:
    return ft.Container(
        content=content,
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_MD,
        ),
        border_radius=tokens.RADIUS_LG,
        **kwargs,
    )


def build_banner_ad(page: ft.Page, unit_id: str | None = None) -> ft.Control:
    """The canonical Sherlock banner builder (components/banner_ad.py).

    Kept here as an alias because a dozen screens still import it from
    styles; new code should import pooled_banner_ad and use a slot. The
    old styles-local body (premium gate, per-render fresh BannerAd) is gone —
    the per-render rebuild was what made the terminal banner flash and look
    like it vanished on the phone.
    """
    from components.banner_ad import build_banner_ad as _build

    return _build(page)


def hardware_badge(accelerator: str, variant: str = "") -> ft.Container:
    """Build a colored hardware chip (CPU=gray, GPU=amber, TPU=blue)."""
    from core.theme import AppColors

    label = "CPU" if accelerator == "NONE" else accelerator
    if variant == "TPU" or accelerator.upper() in ("V5E1", "V6E1"):
        color = AppColors.BADGE_TPU
    elif variant == "GPU" or accelerator not in ("NONE",):
        color = AppColors.BADGE_GPU
    else:
        color = AppColors.BADGE_CPU

    return ft.Container(
        content=ft.Text(
            label,
            size=tokens.FONT_XXS,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.WHITE,
        ),
        bgcolor=color,
        border_radius=tokens.RADIUS_XS,
        padding=ft.Padding(
            tokens.SPACE_SM, tokens.SPACE_XXS, tokens.SPACE_SM, tokens.SPACE_XXS
        ),
    )


def shape_chip(machine_shape: str | None = None) -> ft.Container:
    """Build a machine-shape chip (High RAM=purple, Standard RAM=gray).

    Always rendered, matching upstream's always-show `Shape:` segment.
    Legacy sessions without a shape default to Standard RAM.
    """
    from core.theme import AppColors

    high_ram = str(machine_shape or "").upper() == "HIGH_RAM"
    return ft.Container(
        content=ft.Text(
            "High RAM" if high_ram else "Standard RAM",
            size=tokens.FONT_XXS,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.WHITE,
        ),
        bgcolor=AppColors.BADGE_PAID if high_ram else AppColors.BADGE_CPU,
        border_radius=tokens.RADIUS_XS,
        padding=ft.Padding(
            tokens.SPACE_SM, tokens.SPACE_XXS, tokens.SPACE_SM, tokens.SPACE_XXS
        ),
    )


def status_dot(is_running: bool = False) -> ft.Container:
    """Green pulsing dot for running, gray for idle."""
    from core.theme import AppColors

    return ft.Container(
        width=tokens.ICON_SM - 6,
        height=tokens.ICON_SM - 6,
        border_radius=tokens.RADIUS_PILL,
        bgcolor=AppColors.SUCCESS if is_running else AppColors.BADGE_CPU,
    )


def tip_text(text: str) -> ft.Text:
    """Small contextual help text for non-developer-friendly guidance."""
    return ft.Text(
        text,
        size=tokens.FONT_XS,
        color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
        italic=True,
    )
