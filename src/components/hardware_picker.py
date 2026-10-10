"""Hardware picker — bottom sheet for creating new sessions."""

import flet as ft

from core import constants, tokens
from core.styles import tip_text


def build_hardware_picker(
    on_create=None,
    name_ref=None,
    gpu_ref=None,
    tpu_ref=None,
    hardware_type_ref=None,
    high_mem_ref=None,
    high_mem_default: bool = False,
) -> ft.Container:
    """Build the hardware selection UI for new sessions.

    Shows CPU/GPU/TPU selector with conditional model dropdowns.
    Highlights free tier options and marks paid ones clearly.
    """

    # Session name field
    name_field = ft.TextField(
        ref=name_ref,
        label="Session Name",
        hint_text="Auto-generated if blank",
        prefix_icon=ft.Icons.LABEL_OUTLINE_ROUNDED,
        border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_MD),
        text_size=tokens.FONT_MD,
    )

    def _on_hardware_change(e):
        selected = e.control.selected
        is_gpu = "GPU" in selected
        is_tpu = "TPU" in selected

        gpu_dropdown.visible = is_gpu
        tpu_dropdown.visible = is_tpu
        _refresh_shape_visibility()

        e.control.page.update()

    def _on_gpu_model_change(e):
        _refresh_shape_visibility()
        e.control.page.update()

    def _selected_accelerator() -> str:
        selected = hardware_selector.selected or ["CPU"]
        if "GPU" in selected:
            return (
                gpu_ref.current.value if gpu_ref and gpu_ref.current else "T4"
            ) or "T4"
        if "TPU" in selected:
            return (
                tpu_ref.current.value if tpu_ref and tpu_ref.current else "v5e1"
            ) or "v5e1"
        return "CPU"

    def _is_single_shape() -> bool:
        return _selected_accelerator().upper() in ("L4", "V5E1", "V6E1")

    def _refresh_shape_visibility():
        # Single-shape accelerators (L4, all TPUs) have no High-RAM option on
        # the backend — hide the switch entirely instead of showing a control
        # that silently does nothing. TPU segments hide it outright.
        show = not _is_single_shape()
        high_mem_switch.visible = show
        high_mem_caption.visible = show
        if not show and high_mem_ref and high_mem_ref.current:
            high_mem_ref.current.value = False
        if (
            high_mem_ref
            and high_mem_ref.current
            and hasattr(high_mem_ref.current, "page")
            and high_mem_ref.current.page
        ):
            high_mem_ref.current.page.update()

    def _on_high_mem_change(e):
        e.control.page.update()

    # Hardware type selector
    hardware_selector = ft.SegmentedButton(
        ref=hardware_type_ref,
        selected=["CPU"],
        on_change=_on_hardware_change,
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
        leading_icon=ft.Icons.DEVELOPER_BOARD_ROUNDED,
        border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_MD),
        text_size=tokens.FONT_MD,
        visible=False,
        on_select=_on_gpu_model_change,
    )

    # TPU model dropdown
    tpu_dropdown = ft.Dropdown(
        ref=tpu_ref,
        label="TPU Model",
        options=[
            ft.dropdown.Option(key="v5e1", text="v5e1  ·  Free tier"),
            ft.dropdown.Option(key="v6e1", text="v6e1  ·  Pro"),
        ],
        value="v5e1",
        leading_icon=ft.Icons.BOLT_ROUNDED,
        border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_MD),
        text_size=tokens.FONT_MD,
        visible=False,
    )

    # High-RAM shape switch (Pro/Pro+ entitlement). Hidden outright for
    # single-shape accelerators (L4, all TPUs) — the backend has no High-RAM
    # option there, so no control is shown instead of a dead one.
    high_mem_switch = ft.Switch(
        ref=high_mem_ref,
        label="High-RAM  ·  Pro/Pro+ only",
        value=high_mem_default,
        on_change=_on_high_mem_change,
    )
    high_mem_caption = tip_text("Requires Colab Pro or Pro+ entitlement.")

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
                # High-RAM shape (Pro/Pro+ entitlement; hidden for
                # single-shape accelerators)
                high_mem_switch,
                high_mem_caption,
                ft.Divider(height=tokens.SPACE_LG, color=ft.Colors.TRANSPARENT),
                # Create
                create_btn,
            ],
            spacing=tokens.SPACE_SM,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=0,
    )
