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
            width=320,
            height=50,
            on_error=lambda e: None,
        )
    except Exception as e:
        logger.warning("Failed to load BannerAd: %s", e)
        return ft.Container(width=0, height=0)

    return ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    "SPONSORED",
                    size=tokens.FONT_XXS,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    style=ft.TextStyle(letter_spacing=1),
                ),
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


def build_native_ad(
    page: ft.Page, size: str = "medium", glass: bool = False
) -> ft.Control:
    """Build a native ad container styled to match the app's standard cards."""
    if page.platform not in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
        return ft.Container(width=0, height=0)

    try:
        from flet_ads.types import (
            NativeAdTemplateStyle,
            NativeAdTemplateTextStyle,
            NativeAdTemplateType,
        )

        from services.ad_service import AdService

        ad_service = AdService(page)

        tpl_type = (
            NativeAdTemplateType.MEDIUM
            if size == "medium"
            else NativeAdTemplateType.SMALL
        )

        style = NativeAdTemplateStyle(
            template_type=tpl_type,
            main_bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE)
            if glass
            else ft.Colors.TRANSPARENT,
            corner_radius=tokens.RADIUS_LG,
            call_to_action_text_style=NativeAdTemplateTextStyle(
                bgcolor=ft.Colors.PRIMARY,
                text_color=ft.Colors.ON_PRIMARY,
                size=tokens.FONT_LG,
            ),
            primary_text_style=NativeAdTemplateTextStyle(
                text_color=ft.Colors.ON_SURFACE,
                size=tokens.FONT_XL,
            ),
            secondary_text_style=NativeAdTemplateTextStyle(
                text_color=ft.Colors.with_opacity(0.7, ft.Colors.ON_SURFACE),
                size=tokens.FONT_LG,
            ),
            tertiary_text_style=NativeAdTemplateTextStyle(
                text_color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                size=tokens.FONT_MD,
            ),
        )

        ad = ad_service.get_native_ad(template_style=style)
    except Exception as e:
        logger.warning("Failed to load NativeAd in styles: %s", e)
        return ft.Container(width=0, height=0)

    if glass:
        return ft.Container(
            content=ad,
            alignment=ft.Alignment.CENTER,
            padding=tokens.SPACE_SM,
            border_radius=tokens.RADIUS_LG,
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
            margin=ft.Margin(
                tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
            ),
        )

    return ft.Container(
        content=ad,
        alignment=ft.Alignment.CENTER,
        padding=0,
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
        ),
    )


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
