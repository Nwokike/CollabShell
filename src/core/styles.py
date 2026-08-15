"""Reusable widget factories and card layouts."""

import logging

import flet as ft

from core import tokens
from core.theme import AppColors

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


def section_card(
    title: str, icon: str, content: ft.Control, page: ft.Page | None = None
) -> ft.Container:
    """Frosted card section matching DDGS and SpanInsights standard."""
    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(icon, color=ft.Colors.PRIMARY, size=tokens.ICON_MD),
                        ft.Text(
                            title,
                            size=tokens.FONT_MD,
                            weight=ft.FontWeight.W_600,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                ft.Divider(
                    height=tokens.DIVIDER_THICKNESS,
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_CONTAINER, ft.Colors.ON_SURFACE
                    ),
                ),
                content,
            ],
            spacing=tokens.SPACE_MD,
        ),
        padding=tokens.SPACE_LG,
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE),
        border=ft.Border.all(
            tokens.DIVIDER_THICKNESS,
            ft.Colors.with_opacity(tokens.OPACITY_CONTAINER, ft.Colors.ON_SURFACE),
        ),
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
        ),
    )


def glass_card(content: ft.Control, **kwargs) -> ft.Container:
    return ft.Container(
        content=content,
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_MD,
        ),
        border_radius=tokens.RADIUS_LG,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
        border=ft.Border.all(
            width=1, color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
        ),
        **kwargs,
    )


def build_banner_ad(page: ft.Page, unit_id: str | None = None) -> ft.Control:
    """Build a glass-container-wrapped banner ad (mobile only)."""
    if page.platform not in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
        return ft.Container(width=0, height=0)

    try:
        import flet_ads as fta

        from services.ad_service import AdService

        if not unit_id:
            ad_service = AdService(page)
            unit_id = ad_service.banner_id

        ad = fta.BannerAd(
            unit_id=unit_id,
            width=tokens.BANNER_WIDTH,
            height=tokens.BANNER_HEIGHT,
            on_error=lambda e: None,
        )
    except Exception as e:
        logger.warning("Failed to load BannerAd: %s", e)
        return ft.Container(width=0, height=0)

    return ft.Container(
        content=ft.Column(
            [
                ad,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_XS,
        ),
        alignment=ft.Alignment.CENTER,
        padding=tokens.SPACE_SM,
        border_radius=tokens.RADIUS_LG,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
        ),
    )


def hardware_badge(accelerator: str, variant: str = "") -> ft.Container:
    """Build a colored hardware chip (CPU=gray, GPU=amber, TPU=blue)."""
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


def status_dot(is_running: bool = False) -> ft.Container:
    """Green pulsing dot for running, gray for idle."""
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
