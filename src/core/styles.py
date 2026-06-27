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
                    size=8,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    style=ft.TextStyle(letter_spacing=1),
                ),
                ad,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
        alignment=ft.Alignment.CENTER,
        padding=8,
        border_radius=tokens.RADIUS_LG,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
        ),
    )


def hardware_badge(accelerator: str, variant: str = "") -> ft.Container:
    """Build a colored hardware chip (CPU=gray, GPU=amber, TPU=blue)."""
    from core.theme import AppColors

    label = "CPU" if accelerator == "NONE" else accelerator
    if variant == "TPU" or accelerator in ("V5E1", "V6E1"):
        color = AppColors.BADGE_TPU
    elif variant == "GPU" or accelerator not in ("NONE",):
        color = AppColors.BADGE_GPU
    else:
        color = AppColors.BADGE_CPU

    return ft.Container(
        content=ft.Text(
            label, size=tokens.FONT_XXS, weight=ft.FontWeight.W_700, color="#FFFFFF"
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
        width=10,
        height=10,
        border_radius=5,
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


def standard_brand_appbar(
    title_text: str,
    on_back=None,
    actions=None,
) -> ft.AppBar:
    """Build a consistent, brand-aligned AppBar across all views."""
    left_controls = []
    if on_back:
        left_controls.append(
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK_ROUNDED,
                on_click=on_back,
                tooltip="Back",
                icon_size=20,
            )
        )
    left_controls.append(
        ft.Image(
            src="icon.png",
            width=24,
            height=24,
            fit=ft.BoxFit.CONTAIN,
        )
    )
    left_controls.append(
        ft.Column(
            controls=[
                ft.Text(
                    "CollabShell",
                    size=13,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.ON_SURFACE,
                ),
                ft.Text(
                    "Cloud GPUs",
                    size=8,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=0,
            alignment=ft.MainAxisAlignment.CENTER,
        )
    )

    brand_leading = ft.Container(
        content=ft.Row(
            controls=left_controls,
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(4 if on_back else 12, 0, 0, 0),
    )

    return ft.AppBar(
        leading=brand_leading,
        leading_width=180 if on_back else 150,
        title=ft.Text(
            title_text,
            size=16,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.ON_SURFACE,
        ),
        center_title=True,
        actions=actions or [],
        bgcolor=ft.Colors.TRANSPARENT,
    )
