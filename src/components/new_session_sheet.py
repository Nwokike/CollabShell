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
    storage=None,
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
    high_mem_ref = ft.Ref[ft.Switch]()

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
        high_mem = bool(high_mem_ref.current and high_mem_ref.current.value)

        from core.constants import PAID_TIER_GPU

        paid_gpus = set(PAID_TIER_GPU)
        # v6e1 is a Pro TPU (v5e1 is the only free TPU) — confirmed live:
        # v6e1 returns 400 on free accounts while v5e1 succeeds.
        paid_tpus = {"v6e1"}
        needs_confirm = gpu in paid_gpus or (tpu or "").lower() in paid_tpus or high_mem
        if needs_confirm:

            def _close_confirm(data):
                confirm_dialog.data = data
                confirm_dialog.open = False
                page.update()

            confirm_lines = []
            if gpu in paid_gpus:
                confirm_lines.append(
                    f"{gpu} requires Colab Pro or Pay As You Go and may incur charges."
                )
            if (tpu or "").lower() in paid_tpus:
                confirm_lines.append(
                    f"{tpu} requires Colab Pro and may fail on free accounts."
                )
            if high_mem:
                confirm_lines.append(
                    "High-RAM shape requires Colab Pro or Pro+ entitlement "
                    "and may fail on free accounts."
                )
            # Cached balance line (shared 24h cache with Home + Settings).
            # Never blocks the dialog: omitted when unavailable.
            try:
                from types import SimpleNamespace as _NS

                from services.usage_cache import get_usage_cached

                usage = await get_usage_cached(
                    _NS(colab=colab_service, storage=storage),
                    state.auth_method,
                )
                if usage is not None:
                    confirm_lines.append(
                        f"Current balance: {float(usage.get('balance', 0.0)):.2f} "
                        "compute units."
                    )
            except Exception:
                pass
            confirm_dialog = ft.AlertDialog(
                modal=True,
                on_dismiss=lambda e: _close_confirm("cancel"),
                title=ft.Text("Paid Runtime Warning"),
                content=ft.Text("\n\n".join(confirm_lines) + "\n\nContinue?"),
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
                "Attempting to create session: %s (GPU=%s, TPU=%s, high_mem=%s)",
                name,
                gpu,
                tpu,
                high_mem,
            )
            result = await colab_service.new_session(
                name=name or None,
                gpu=gpu if gpu else None,
                tpu=tpu if tpu else None,
                auth_method=state.auth_method,
                high_mem=high_mem,
            )
            logger.info(
                "Session created successfully: name=%s variant=%s accelerator=%s shape=%s",
                result["name"],
                result["variant"],
                result["accelerator"],
                result["machine_shape"],
            )
            loading_dialog.open = False
            page.update()

            if snack_func:
                snack_func(f"✅ Session '{result['name']}' created!")

            from services.colab.session_ops import SessionListError

            try:
                sessions = await colab_service.list_sessions(
                    auth_method=state.auth_method,
                )
            except SessionListError as ex:
                logger.warning(
                    "Session created but assignment verification failed: %s", ex
                )
                sessions = ex.last_known_sessions
            state.active_sessions = list(sessions)

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
                msg = str(ex)
                if "Allocation refused (precondition failed)" in msg:
                    if high_mem:
                        msg += (
                            " If you requested High RAM, retry as Standard RAM — "
                            "High RAM requires Colab Pro/Pro+."
                        )
                    snack_func(f"❌ {msg}")
                elif (
                    "High-RAM is not available" in msg
                    or "rejected" in msg
                    and "quota or entitlement" in msg
                ):
                    snack_func(f"❌ {msg}")
                else:
                    snack_func(f"❌ {ex}")
        state.is_provisioning = False
        page.update()

    picker = build_hardware_picker(
        on_create=lambda e: page.run_task(_on_create, e),
        name_ref=name_ref,
        gpu_ref=gpu_ref,
        tpu_ref=tpu_ref,
        hardware_type_ref=hardware_type_ref,
        high_mem_ref=high_mem_ref,
        high_mem_default=bool(getattr(state, "default_high_mem", False)),
    )

    hw_dialog = ft.AlertDialog(
        title=ft.Text("New Session", weight=ft.FontWeight.W_700),
        content=picker,
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(hw_dialog)
