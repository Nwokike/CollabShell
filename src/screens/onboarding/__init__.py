"""OnboardingScreen — First-launch presentation with Google OAuth2 authentication."""

from __future__ import annotations

import logging

import flet as ft

from core import constants, tokens
from core.theme import AppColors
from screens.onboarding.slides import (
    build_page_1,
    build_page_2,
    build_page_3,
)
from state import AppStateCtx, ServiceCtx

logger = logging.getLogger("OnboardingScreen")

TOTAL_SLIDES = 3


@ft.component
def OnboardingScreen() -> ft.Control:
    """Build the onboarding presentation with Google Sign-In."""
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    page = ft.context.page

    slide_index, set_slide_index = ft.use_state(0)
    auth_code, set_auth_code = ft.use_state("")
    auth_status, set_auth_status = ft.use_state("")
    auth_status_color, set_auth_status_color = ft.use_state(AppColors.SUCCESS)
    is_loading_auth, set_is_loading_auth = ft.use_state(False)
    show_verify, set_show_verify = ft.use_state(False)

    auth_code_ref = ft.use_ref(None)
    is_submitting_ref = ft.use_ref(False)

    # ── Auth handlers ─────────────────────────────────────────────────────────
    async def _start_auth(e=None):
        if not services.colab:
            return
        set_is_loading_auth(True)
        set_auth_status("")

        try:
            auth_url = await services.colab.get_auth_url()
            await ft.UrlLauncher().launch_url(auth_url)
            set_show_verify(True)
            set_is_loading_auth(False)
        except Exception as ex:
            logger.error("OAuth URL generation failed: %s", ex)
            set_auth_status(f"Error: {ex}")
            set_auth_status_color(AppColors.ERROR)
            set_is_loading_auth(False)

    async def _submit_code(e=None):
        if is_submitting_ref.current:
            return

        code = auth_code.strip()
        if not code and auth_code_ref.current and auth_code_ref.current.value:
            code = auth_code_ref.current.value.strip()

        if not code:
            set_auth_status("Please paste your authorization code first.")
            set_auth_status_color(AppColors.WARNING)
            return

        if not services.colab:
            return

        is_submitting_ref.current = True
        set_is_loading_auth(True)
        set_auth_status("Verifying code...")
        set_auth_status_color(ft.Colors.ON_SURFACE_VARIANT)

        try:
            result = await services.colab.authenticate_oauth2(code)
            if result.get("success"):
                state.is_authenticated = True
                state.auth_email = result.get("email", "")
                set_auth_status(f"✅ Signed in as {state.auth_email}")
                set_auth_status_color(AppColors.SUCCESS)
                set_is_loading_auth(False)
            else:
                err = result.get("error", "Invalid authorization code")
                set_auth_status(f"❌ {err}")
                set_auth_status_color(AppColors.ERROR)
                set_is_loading_auth(False)
                is_submitting_ref.current = False
        except Exception as ex:
            logger.error("OAuth verification failed: %s", ex)
            set_auth_status(f"❌ {ex}")
            set_auth_status_color(AppColors.ERROR)
            set_is_loading_auth(False)
            is_submitting_ref.current = False

    # ── Navigation handlers ───────────────────────────────────────────────────
    async def _on_get_started():
        state.onboarding_done = True
        if services.storage:
            await services.storage.set(constants.STORAGE_ONBOARDING_DONE, "true")
        page.update()

    def _on_next(e=None):
        if slide_index < TOTAL_SLIDES - 1:
            set_slide_index(slide_index + 1)
        else:
            if state.is_authenticated:
                page.run_task(_on_get_started)

    def _on_back(e=None):
        if slide_index > 0:
            set_slide_index(slide_index - 1)

    def _on_swipe(e: ft.DragEndEvent):
        v = e.primary_velocity or 0
        if v < -200 and slide_index < TOTAL_SLIDES - 1:
            set_slide_index(slide_index + 1)
        elif v > 200 and slide_index > 0:
            set_slide_index(slide_index - 1)

    # ── Slide builders ────────────────────────────────────────────────────────
    def _build_slide(index: int) -> ft.Control:
        if index == 0:
            return build_page_1()
        elif index == 1:
            return build_page_2()
        else:
            return build_page_3(
                auth_code_ref=auth_code_ref,
                auth_code_val=auth_code,
                on_auth_code_change=lambda e: set_auth_code(e.control.value or ""),
                show_verify=show_verify,
                auth_status=auth_status,
                auth_status_color=auth_status_color,
                is_loading_auth=is_loading_auth,
                on_start_auth=lambda e: page.run_task(_start_auth, e),
                on_submit_code=lambda e: page.run_task(_submit_code, e),
            )

    # ── Page indicator dots ───────────────────────────────────────────────────
    dots = [
        ft.Container(
            width=10 if i == slide_index else 6,
            height=6,
            border_radius=3,
            bgcolor=ft.Colors.PRIMARY
            if i == slide_index
            else ft.Colors.with_opacity(0.25, ft.Colors.ON_SURFACE),
            animate=ft.Animation(200, ft.AnimationCurve.EASE_IN_OUT),
        )
        for i in range(TOTAL_SLIDES)
    ]

    # ── Bottom navigation row ─────────────────────────────────────────────────
    is_last = slide_index == TOTAL_SLIDES - 1
    next_btn_text = "Get Started" if is_last else "Next"
    next_btn_disabled = is_last and not state.is_authenticated

    nav_row = ft.Container(
        content=ft.Row(
            controls=[
                ft.TextButton(
                    content=ft.Text("Back"),
                    on_click=_on_back,
                    visible=slide_index > 0,
                ),
                ft.Row(
                    controls=dots,
                    spacing=tokens.SPACE_SM,
                ),
                ft.FilledButton(
                    content=ft.Text(next_btn_text),
                    disabled=next_btn_disabled,
                    on_click=_on_next,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_XL
        ),
    )

    slide_area = ft.GestureDetector(
        content=ft.Container(
            content=_build_slide(slide_index),
            expand=True,
            padding=ft.Padding(tokens.SPACE_XL, 0, tokens.SPACE_XL, 0),
        ),
        on_horizontal_drag_end=_on_swipe,
        expand=True,
    )

    return ft.SafeArea(
        content=ft.Column(
            controls=[
                slide_area,
                nav_row,
            ],
            expand=True,
            spacing=0,
        ),
        expand=True,
    )


__all__ = ["OnboardingScreen"]
