"""Hardware picker — bottom sheet for creating new sessions."""

import flet as ft

from core import tokens, constants
from core.styles import tip_text


def build_hardware_picker(
    on_create=None,
    name_ref=None,
    gpu_ref=None,
    tpu_ref=None,
) -> ft.Container:
    """Build the hardware selection UI for new sessions.

    Shows CPU/GPU/TPU selector with conditional model dropdowns.
    Highlights free tier options and marks paid ones clearly.
    """
    hardware_type_ref = ft.Ref[ft.SegmentedButton]()

    # Session name field
    name_field = ft.TextField(
        ref=name_ref,
        label="Session Name",
        hint_text="Auto-generated if blank",
        prefix_icon=ft.Icons.LABEL_OUTLINE_ROUNDED,
        border_radius=tokens.RADIUS_MD,
        text_size=tokens.FONT_MD,
    )

    # Hardware type selector
    hardware_selector = ft.SegmentedButton(
        ref=hardware_type_ref,
        selected={"CPU"},
        segments=[
            ft.Segment(
                value="CPU", label=ft.Text("CPU"), icon=ft.Icon(ft.Icons.MEMORY_ROUNDED)
            ),
            ft.Segment(
                value="GPU",
                label=ft.Text("GPU"),
                icon=ft.Icon(ft.Icons.DEVELOPER_BOARD_ROUNDED),
            ),
            ft.Segment(
                value="TPU", label=ft.Text("TPU"), icon=ft.Icon(ft.Icons.BOLT_ROUNDED)
            ),
        ],
    )

    # GPU model dropdown
    gpu_dropdown = ft.Dropdown(
        ref=gpu_ref,
        label="GPU Model",
        options=[
            ft.dropdown.Option(key="T4", text="T4  ·  Free tier"),
            ft.dropdown.Option(key="L4", text="L4  ·  Pro"),
            ft.dropdown.Option(key="G4", text="G4  ·  Pro"),
            ft.dropdown.Option(key="A100", text="A100  ·  Pro / Pay As You Go"),
            ft.dropdown.Option(key="H100", text="H100  ·  Pro / Pay As You Go"),
        ],
        value="T4",
        prefix_icon=ft.Icons.DEVELOPER_BOARD_ROUNDED,
        border_radius=tokens.RADIUS_MD,
        text_size=tokens.FONT_MD,
    )

    # TPU model dropdown
    tpu_dropdown = ft.Dropdown(
        ref=tpu_ref,
        label="TPU Model",
        options=[
            ft.dropdown.Option(key="v5e1", text="v5e1  ·  Free tier"),
            ft.dropdown.Option(key="v6e1", text="v6e1  ·  Free tier"),
        ],
        value="v5e1",
        prefix_icon=ft.Icons.BOLT_ROUNDED,
        border_radius=tokens.RADIUS_MD,
        text_size=tokens.FONT_MD,
    )

    # Create button
    create_btn = ft.FilledButton(
        content=ft.Text("Create Session"),
        icon=ft.Icons.ROCKET_LAUNCH_ROUNDED,
        on_click=on_create,
        style=ft.ButtonStyle(
            padding=ft.Padding(
                tokens.SPACE_XL, tokens.SPACE_MD, tokens.SPACE_XL, tokens.SPACE_MD
            )
        ),
        width=float("inf"),
    )

    return ft.Container(
        content=ft.Column(
            controls=[
                # Header
                ft.Text(
                    "New Session",
                    size=tokens.FONT_XXL,
                    weight=ft.FontWeight.W_700,
                ),
                ft.Text(
                    "Create a cloud runtime to execute Python code",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Divider(height=tokens.SPACE_LG, color=ft.Colors.TRANSPARENT),
                # Name
                name_field,
                tip_text(constants.TIP_SESSION_NAME),
                ft.Divider(height=tokens.SPACE_SM, color=ft.Colors.TRANSPARENT),
                # Hardware
                ft.Text("Hardware", size=tokens.FONT_MD, weight=ft.FontWeight.W_600),
                hardware_selector,
                tip_text(constants.TIP_CPU),
                ft.Divider(height=tokens.SPACE_SM, color=ft.Colors.TRANSPARENT),
                # GPU dropdown (shown dynamically via main.py logic)
                gpu_dropdown,
                # TPU dropdown
                tpu_dropdown,
                ft.Divider(height=tokens.SPACE_LG, color=ft.Colors.TRANSPARENT),
                # Create
                create_btn,
            ],
            spacing=tokens.SPACE_SM,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=ft.Padding(
            tokens.SPACE_XL, tokens.SPACE_XL, tokens.SPACE_XL, tokens.SPACE_XL
        ),
    )
