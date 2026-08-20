"""Session card — reusable card for session list items."""

import flet as ft

from core import tokens
from core.styles import hardware_badge, status_dot
from core.theme import adaptive_glass_bg, adaptive_glass_border


def build_session_card(
    session: dict,
    on_click=None,
) -> ft.Container:
    """Build a session card showing name, hardware, status, and last execution.

    session dict keys: name, accelerator, variant, status, running, last_execution, accelerator_label
    """
    name = session.get("name", "?")
    variant = session.get("variant", "DEFAULT")
    accel_str = session.get("accelerator_label") or session.get("accelerator", "NONE")
    status = session.get("status", "IDLE")
    running = session.get("running")
    last_exec = session.get("last_execution")
    is_running = running is not None

    # Last execution subtitle
    subtitle = ""
    if last_exec:
        subtitle = f"Last: {last_exec.get('file', '')} at {last_exec.get('time', '')}"
    elif status == "IDLE":
        subtitle = "Ready for commands"

    return ft.Container(
        content=ft.Row(
            controls=[
                # Status dot
                status_dot(is_running),
                # Session info
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Text(
                                    name,
                                    size=tokens.FONT_LG,
                                    weight=ft.FontWeight.W_600,
                                ),
                                hardware_badge(accel_str, variant),
                            ],
                            spacing=tokens.SPACE_SM,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text(
                            subtitle,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=tokens.SPACE_XXS,
                    expand=True,
                ),
                # Chevron
                ft.Icon(
                    ft.Icons.CHEVRON_RIGHT_ROUNDED,
                    size=tokens.ICON_LG,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_MD,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD
        ),
        border_radius=tokens.RADIUS_MD,
        bgcolor=adaptive_glass_bg(),
        border=ft.Border.all(1, adaptive_glass_border()),
        margin=ft.Margin(tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, 0),
        on_click=on_click,
        ink=True,
    )
