import flet as ft
from core import tokens


def build_brand_header(
    show_tagline: bool = True, spacing_below: bool = True
) -> ft.Container:
    """Build the reusable hero header matching SpanInsight's style."""
    controls = [
        ft.Container(height=tokens.SPACE_LG),
        ft.Image(
            src="icon.png",
            width=tokens.ICON_XXXL,
            height=tokens.ICON_XXXL,
            fit=ft.BoxFit.CONTAIN,
        ),
    ]

    if show_tagline:
        controls.extend(
            [
                ft.Container(height=tokens.SPACE_SM),
                ft.Text(
                    "Cloud GPUs from your phone",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
            ]
        )

    if spacing_below:
        controls.append(ft.Container(height=tokens.SPACE_XL))

    return ft.Container(
        content=ft.Column(
            controls=controls,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
    )
