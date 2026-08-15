"""OnboardingScreen — 3-slide onboarding with OAuth2 auth flow."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.theme import AppColors
from screens.onboarding.slides import build_page_1, build_page_2
from state import AppStateCtx, ServiceCtx

# ── Slide 3 content (auth flow, uses local state values) ─────────────────────


def _build_slide_3(
    auth_url_visible: bool,
    code_visible: bool,
    status_text: str,
    status_color,
    btn_text: str,
    btn_disabled: bool,
    on_sign_in,
    on_submit,
    code_ref: ft.Ref,
) -> ft.Control:
    return ft.Column(
        controls=[
            ft.Icon(ft.Icons.LOCK_OPEN_ROUNDED, size=80, color=ft.Colors.PRIMARY),
            ft.Text(
                constants.LBL_SIGN_IN_TITLE,
                size=tokens.FONT_XL,
                weight=ft.FontWeight.BOLD,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Text(
                constants.LBL_SIGN_IN_BODY,
                size=tokens.FONT_SM,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.FilledButton(
                content=ft.Text(btn_text),
                ref=None,
                icon=ft.Icons.LOGIN_ROUNDED,
                width=float("inf"),
                disabled=btn_disabled,
                on_click=on_sign_in,
                style=ft.ButtonStyle(
                    padding=ft.Padding(
                        tokens.SPACE_XL,
                        tokens.SPACE_MD,
                        tokens.SPACE_XL,
                        tokens.SPACE_MD,
                    ),
                ),
            ),
            ft.Text(
                "Paste the authorization code below." if auth_url_visible else "",
                size=tokens.FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align=ft.TextAlign.CENTER,
                visible=auth_url_visible,
            ),
            ft.TextField(
                ref=code_ref,
                label="Paste authorization code",
                prefix_icon=ft.Icons.KEY_ROUNDED,
                border_radius=tokens.RADIUS_MD,
                text_size=tokens.FONT_MD,
                visible=code_visible,
                on_submit=on_submit,
            ),
            ft.FilledTonalButton(
                content=ft.Text("Verify Code"),
                icon=ft.Icons.VERIFIED_ROUNDED,
                visible=code_visible,
                on_click=on_submit,
            ),
            ft.Text(
                status_text,
                size=tokens.FONT_SM,
                color=status_color,
                text_align=ft.TextAlign.CENTER,
                visible=bool(status_text),
            ),
            ft.Divider(height=tokens.SPACE_SM),
            ft.Text(
                "Disclaimer: Unofficial client application. Not affiliated with, authorized, sponsored, or endorsed by Google LLC.",
                size=tokens.FONT_XXS,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align=ft.TextAlign.CENTER,
                italic=True,
            ),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=tokens.SPACE_SM,
    )


# ── OnboardingScreen ──────────────────────────────────────────────────────────


@ft.component
def OnboardingScreen() -> ft.Control:
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    page = ft.context.page

    page_idx, set_page = ft.use_state(0)
    auth_url_visible, set_url_visible = ft.use_state(False)
    code_visible, set_code_visible = ft.use_state(False)
    status_text, set_status = ft.use_state("")
    status_color, set_status_color = ft.use_state(AppColors.SUCCESS)
    btn_text, set_btn_text = ft.use_state(constants.LBL_SIGN_IN)
    btn_disabled, set_btn_disabled = ft.use_state(False)

    code_ref = ft.use_ref(ft.Ref)

    # ── Auth handlers ─────────────────────────────────────────────────────────
    async def _start_auth(e=None):
        set_btn_disabled(True)
        set_btn_text("Generating link...")
        try:
            url = await services.colab.get_auth_url()
            await ft.UrlLauncher().launch_url(url)
            set_url_visible(True)
            set_code_visible(True)
            set_btn_text("Link opened in browser")
        except Exception as ex:
            set_btn_disabled(False)
            set_btn_text(constants.LBL_SIGN_IN)
            set_status(f"Error: {ex}")
            set_status_color(AppColors.ERROR)

    async def _submit_code(e=None):
        code_ctrl = code_ref.current
        code = (code_ctrl.value or "").strip() if code_ctrl else ""
        if not code:
            return
        set_status("Verifying...")
        set_status_color(ft.Colors.ON_SURFACE_VARIANT)
        result = await services.colab.authenticate_oauth2(code)
        if result.get("success"):
            state.is_authenticated = True
            state.auth_email = result.get("email", "")
            set_status(f"✅ Signed in as {result['email']}")
            set_status_color(AppColors.SUCCESS)
        else:
            set_status(f"❌ {result.get('error', 'Unknown error')}")
            set_status_color(AppColors.ERROR)

    # ── Navigation ────────────────────────────────────────────────────────────
    async def _on_get_started(e=None):
        state.onboarding_done = True
        await services.storage.set(constants.STORAGE_ONBOARDING_DONE, "true")

    def _on_next(e=None):
        if page_idx < 2:
            set_page(page_idx + 1)

    def _on_back(e=None):
        if page_idx > 0:
            set_page(page_idx - 1)

    def _on_swipe(e: ft.DragEndEvent):
        if e.primary_velocity is not None:
            if e.primary_velocity < -200:
                _on_next()
            elif e.primary_velocity > 200:
                _on_back()

    # ── Slide content ─────────────────────────────────────────────────────────
    if page_idx == 0:
        slide_content = build_page_1()
    elif page_idx == 1:
        slide_content = build_page_2()
    else:
        slide_content = _build_slide_3(
            auth_url_visible=auth_url_visible,
            code_visible=code_visible,
            status_text=status_text,
            status_color=status_color,
            btn_text=btn_text,
            btn_disabled=btn_disabled,
            on_sign_in=lambda e: page.run_task(_start_auth, e),
            on_submit=lambda e: page.run_task(_submit_code, e),
            code_ref=code_ref,
        )

    # ── Dot indicators ────────────────────────────────────────────────────────
    dots = [
        ft.Container(
            width=10 if i == page_idx else 6,
            height=6,
            border_radius=3,
            bgcolor=ft.Colors.PRIMARY
            if i == page_idx
            else ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE),
        )
        for i in range(3)
    ]

    # ── Next/Get Started button ───────────────────────────────────────────────
    if page_idx == 2:
        next_btn = ft.FilledButton(
            content=ft.Text("Get Started"),
            disabled=not state.is_authenticated,
            on_click=lambda e: page.run_task(_on_get_started, e),
        )
    else:
        next_btn = ft.FilledButton(content=ft.Text("Next"), on_click=_on_next)

    return ft.GestureDetector(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=slide_content,
                    expand=True,
                    padding=ft.Padding(
                        tokens.SPACE_XL,
                        tokens.SPACE_XL,
                        tokens.SPACE_XL,
                        tokens.SPACE_MD,
                    ),
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=dots,
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=tokens.SPACE_SM,
                            ),
                            ft.Row(
                                controls=[
                                    ft.TextButton(
                                        "Back", on_click=_on_back, visible=page_idx > 0
                                    ),
                                    ft.Container(expand=True),
                                    next_btn,
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                        ],
                        spacing=tokens.SPACE_SM,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_LG,
                        tokens.SPACE_MD,
                        tokens.SPACE_LG,
                        tokens.SPACE_LG,
                    ),
                ),
            ],
            expand=True,
        ),
        on_horizontal_drag_end=_on_swipe,
        expand=True,
    )
