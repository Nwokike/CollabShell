import asyncio
import logging

import flet as ft

from components.hardware_picker import build_hardware_picker
from core import tokens

logger = logging.getLogger("new_session_sheet")


def show_new_session_sheet(
    page: ft.Page,
    state,
    colab_service,
    ad_service,
    navigate=None,
    route_change=None,
    snack_func=None,
    mode=None,
    ignore_warning=False,
    on_session_created=None,
):
    def _close_limit_dialog(e=None):
        limit_dialog.open = False
        page.update()

    def _on_proceed(e):
        _close_limit_dialog()
        show_new_session_sheet(
            page,
            state,
            colab_service,
            ad_service,
            navigate=navigate,
            route_change=route_change,
            snack_func=snack_func,
            mode=mode,
            ignore_warning=True,
            on_session_created=on_session_created,
        )

    if not ignore_warning and len(state.active_sessions) >= 3:
        limit_dialog = ft.AlertDialog(
            title=ft.Text("Session Limit", weight=ft.FontWeight.BOLD),
            content=ft.Text(
                "You already have 3 active sessions. Creating another session might fail with a quota error unless you have a Google Colab Pro subscription.\n\nDo you want to proceed?"
            ),
            actions=[
                ft.TextButton("Cancel", on_click=_close_limit_dialog),
                ft.TextButton("Proceed", on_click=_on_proceed),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(limit_dialog)
        return

    name_ref = ft.Ref[ft.TextField]()
    gpu_ref = ft.Ref[ft.Dropdown]()
    tpu_ref = ft.Ref[ft.Dropdown]()
    hardware_type_ref = ft.Ref[ft.SegmentedButton]()

    async def _on_create(e):
        name = name_ref.current.value.strip() if name_ref.current else ""

        selected_hw = (
            next(iter(hardware_type_ref.current.selected))
            if hardware_type_ref.current and hardware_type_ref.current.selected
            else "CPU"
        )

        gpu = (
            gpu_ref.current.value
            if (gpu_ref.current and selected_hw == "GPU")
            else None
        )
        tpu = (
            tpu_ref.current.value
            if (tpu_ref.current and selected_hw == "TPU")
            else None
        )

        paid_gpus = {"L4", "G4", "A100", "H100"}
        if gpu in paid_gpus:

            def _close_confirm(data):
                confirm_dialog.data = data
                confirm_dialog.open = False
                page.update()

            confirm_dialog = ft.AlertDialog(
                modal=True,
                on_dismiss=lambda e: _close_confirm("cancel"),
                title=ft.Text("Paid Runtime Warning"),
                content=ft.Text(
                    f"{gpu} requires Colab Pro or Pay As You Go and may incur charges. Continue?"
                ),
                actions=[
                    ft.TextButton(
                        "Cancel",
                        on_click=lambda e: _close_confirm("cancel"),
                    ),
                    ft.FilledButton(
                        "Continue",
                        on_click=lambda e: _close_confirm("continue"),
                    ),
                ],
            )
            page.show_dialog(confirm_dialog)

            while getattr(confirm_dialog, "data", None) is None:
                await asyncio.sleep(0.1)
            if confirm_dialog.data == "cancel":
                return

        hw_dialog.open = False
        page.update()
        if ad_service:
            await ad_service.show_interstitial()

        loading_dialog = ft.AlertDialog(
            modal=True,
            content=ft.Container(
                content=ft.Row(
                    [
                        ft.ProgressRing(
                            width=tokens.SPINNER_MD,
                            height=tokens.SPINNER_MD,
                            stroke_width=3,
                        ),
                        ft.Text(
                            "Creating session...",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_500,
                        ),
                    ],
                    spacing=tokens.SPACE_MD,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                padding=ft.Padding(
                    tokens.SPACE_XL,
                    tokens.SPACE_LG,
                    tokens.SPACE_XL,
                    tokens.SPACE_LG,
                ),
            ),
        )
        page.show_dialog(loading_dialog)
        state.is_provisioning = True

        try:
            logger.info(
                "Attempting to create session: %s (GPU=%s, TPU=%s)", name, gpu, tpu
            )
            result = await colab_service.new_session(
                name=name or None,
                gpu=gpu if gpu else None,
                tpu=tpu if tpu else None,
                auth_method=state.auth_method,
                keep_alive=state.keep_alive_enabled,
            )
            logger.info("Session created successfully: %s", result)
            loading_dialog.open = False
            page.update()

            if snack_func:
                snack_func(f"✅ Session '{result['name']}' created!")

            sessions = await colab_service.list_sessions(
                auth_method=state.auth_method,
            )
            state.active_sessions = sessions or []

            if on_session_created:
                on_session_created(result["name"])
            elif navigate and mode:
                import urllib.parse

                encoded_session = urllib.parse.quote(result["name"])
                if mode == "notebook":
                    await navigate(f"/session?session={encoded_session}")
                elif mode == "terminal":
                    await navigate(f"/session?session={encoded_session}&tab=terminal")
                elif mode == "files":
                    await navigate(f"/files?session={encoded_session}")
            elif route_change:
                await route_change()
        except Exception as ex:
            logger.exception("Failed to create session")
            loading_dialog.open = False
            page.update()
            if snack_func:
                snack_func(f"❌ {ex}")
        state.is_provisioning = False
        page.update()

    picker = build_hardware_picker(
        on_create=lambda e: page.run_task(_on_create, e),
        name_ref=name_ref,
        gpu_ref=gpu_ref,
        tpu_ref=tpu_ref,
        hardware_type_ref=hardware_type_ref,
    )

    hw_dialog = ft.AlertDialog(
        title=ft.Text("New Session", weight=ft.FontWeight.W_700),
        content=picker,
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(hw_dialog)
