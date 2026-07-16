"""Onboarding view — 3-page welcome flow with OAuth sign-in."""

from __future__ import annotations

import flet as ft

from core import tokens, constants
from core.theme import AppColors
from components.brand_header import build_brand_header


def build_onboarding_view(
    page: ft.Page,
    colab_service,
    state,
    storage,
    on_complete=None,
    snack=None,
) -> ft.View:
    """Build the onboarding view with swipeable slides and OAuth2 integration."""

    current_page = {"index": 0}
    indicator_row = ft.Ref[ft.Row]()
    slide_container = ft.Ref[ft.Container]()
    next_btn = ft.Ref[ft.FilledButton]()
    back_btn = ft.Ref[ft.TextButton]()

    # Refs for Page 3 OAuth
    sign_in_btn = ft.Ref[ft.FilledButton]()
    auth_code_field = ft.Ref[ft.TextField]()
    auth_status_text = ft.Ref[ft.Text]()
    auth_url_text = ft.Ref[ft.Text]()
    verify_btn = ft.Ref[ft.FilledTonalButton]()

    # ── Page 1 Content ──
    def _feature_row(icon, title, subtitle):
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(
                            icon, size=tokens.ICON_XL, color=ft.Colors.PRIMARY
                        ),
                        width=tokens.CARD_ICON_CONTAINER,
                        height=tokens.CARD_ICON_CONTAINER,
                        border_radius=tokens.RADIUS_MD,
                        bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                title, size=tokens.FONT_LG, weight=ft.FontWeight.W_600
                            ),
                            ft.Text(
                                subtitle,
                                size=tokens.FONT_SM,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=tokens.SPACE_XXS,
                        expand=True,
                    ),
                ],
                spacing=tokens.SPACE_LG,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(0, tokens.SPACE_SM, 0, tokens.SPACE_SM),
        )

    def _build_page_1():
        return ft.Column(
            controls=[
                build_brand_header(),
                ft.Container(height=tokens.SPACE_MD),
                _feature_row(
                    ft.Icons.CODE_ROUNDED,
                    "Interactive Notebook",
                    "Write, organize, and execute code cells with real-time output",
                ),
                _feature_row(
                    ft.Icons.TERMINAL_ROUNDED,
                    "Real PTY Terminal",
                    "Access a raw, interactive Linux bash shell for your runtime environment",
                ),
                _feature_row(
                    ft.Icons.FOLDER_ROUNDED,
                    "Cloud File Explorer",
                    "Upload, download, and manage remote workspace files and folders",
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        )

    # ── Page 2 Content ──
    def _build_page_2():
        return ft.Column(
            controls=[
                ft.Container(height=tokens.SPACE_XL),
                ft.Icon(
                    ft.Icons.ROCKET_LAUNCH_ROUNDED,
                    size=tokens.ICON_XXXL,
                    color=ft.Colors.PRIMARY,
                ),
                ft.Text(
                    "How it works",
                    size=tokens.FONT_XXL,
                    weight=ft.FontWeight.W_700,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=tokens.SPACE_SM),
                _feature_row(
                    ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED,
                    "1. Connect Session",
                    "Start CPU (free), GPU (T4/A100/H100), or TPU session runtimes.",
                ),
                _feature_row(
                    ft.Icons.NOTEBOOK_OUTLINED,
                    "2. Run Cells",
                    "Edit and run interactive code blocks in the notebook view.",
                ),
                _feature_row(
                    ft.Icons.TERMINAL_ROUNDED,
                    "3. Run Shell Commands",
                    "Execute bash scripts, clone git repos, or run interactive CLIs in terminal.",
                ),
                _feature_row(
                    ft.Icons.CLOUD_SYNC_ROUNDED,
                    "4. Sync Files",
                    "Browse directory structures, download results, or upload datasets.",
                ),
                ft.Container(height=tokens.SPACE_SM),
                ft.Container(
                    content=ft.Text(
                        "💡 CPU sessions are always free. GPU/TPU have usage limits on the free tier.",
                        size=tokens.FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_LG,
                        tokens.SPACE_MD,
                        tokens.SPACE_LG,
                        tokens.SPACE_MD,
                    ),
                    bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
                    border_radius=tokens.RADIUS_MD,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        )

    # ── Page 3 Content ──
    async def _start_auth():
        try:
            if sign_in_btn.current:
                sign_in_btn.current.disabled = True
                sign_in_btn.current.content = ft.Text("Generating link...")
            page.update()

            url = await colab_service.get_auth_url()
            await ft.UrlLauncher().launch_url(url)

            if auth_url_text.current:
                auth_url_text.current.value = "Paste the authorization code below."
                auth_url_text.current.visible = True
            if auth_code_field.current:
                auth_code_field.current.visible = True
            if verify_btn.current:
                verify_btn.current.visible = True

            if sign_in_btn.current:
                sign_in_btn.current.content = ft.Text("Link opened in browser")
            page.update()
        except Exception as ex:
            if sign_in_btn.current:
                sign_in_btn.current.disabled = False
                sign_in_btn.current.content = ft.Text(constants.LBL_SIGN_IN)
            if auth_status_text.current:
                auth_status_text.current.value = f"Error: {ex}"
                auth_status_text.current.color = AppColors.ERROR
                auth_status_text.current.visible = True
            page.update()

    async def _submit_code():
        code = auth_code_field.current.value.strip() if auth_code_field.current else ""
        if not code:
            return

        if auth_status_text.current:
            auth_status_text.current.value = "Verifying..."
            auth_status_text.current.color = ft.Colors.ON_SURFACE_VARIANT
            auth_status_text.current.visible = True
        page.update()

        result = await colab_service.authenticate_oauth2(code)
        if result["success"]:
            state.is_authenticated = True
            state.auth_email = result["email"]
            if auth_status_text.current:
                auth_status_text.current.value = f"✅ Signed in as {result['email']}"
                auth_status_text.current.color = AppColors.SUCCESS
                auth_status_text.current.visible = True
            if next_btn.current:
                next_btn.current.disabled = False
        else:
            if auth_status_text.current:
                auth_status_text.current.value = f"❌ {result['error']}"
                auth_status_text.current.color = AppColors.ERROR
                auth_status_text.current.visible = True
        page.update()

    def _build_page_3():
        return ft.Column(
            controls=[
                ft.Container(height=tokens.SPACE_XL),
                ft.Icon(
                    ft.Icons.LOCK_OPEN_ROUNDED,
                    size=tokens.ICON_XXXL,
                    color=ft.Colors.PRIMARY,
                ),
                ft.Text(
                    "Sign in to Google",
                    size=tokens.FONT_XXL,
                    weight=ft.FontWeight.W_700,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Required to create and manage Collab Shell sessions",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=tokens.SPACE_LG),
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.CHECK_CIRCLE_ROUNDED,
                                size=tokens.ICON_MD,
                                color=AppColors.SUCCESS,
                            ),
                            ft.Text(
                                "Colab CLI ready",
                                size=tokens.FONT_SM,
                            ),
                        ],
                        spacing=tokens.SPACE_SM,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_LG,
                        tokens.SPACE_MD,
                        tokens.SPACE_LG,
                        tokens.SPACE_MD,
                    ),
                    bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
                    border_radius=tokens.RADIUS_MD,
                ),
                ft.Container(height=tokens.SPACE_LG),
                ft.Text(
                    "💡 IMPORTANT: A browser will open over the app. After copying the code, press the 'X' button at the top left to close the browser and return here.",
                    size=tokens.FONT_XS,
                    color=AppColors.WARNING,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=tokens.SPACE_SM),
                # Sign in button
                ft.FilledButton(
                    content=ft.Text(constants.LBL_SIGN_IN),
                    ref=sign_in_btn,
                    icon=ft.Icons.LOGIN_ROUNDED,
                    width=float("inf"),
                    style=ft.ButtonStyle(
                        padding=ft.Padding(
                            tokens.SPACE_XL,
                            tokens.SPACE_MD,
                            tokens.SPACE_XL,
                            tokens.SPACE_MD,
                        ),
                    ),
                    on_click=lambda e: page.run_task(_start_auth),
                ),
                # Auth URL display
                ft.Text(
                    ref=auth_url_text,
                    value="",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                    selectable=True,
                    visible=False,
                ),
                # Auth code input
                ft.TextField(
                    ref=auth_code_field,
                    label="Paste authorization code",
                    prefix_icon=ft.Icons.KEY_ROUNDED,
                    border_radius=tokens.RADIUS_MD,
                    text_size=tokens.FONT_MD,
                    visible=False,
                    on_submit=lambda e: page.run_task(_submit_code),
                ),
                ft.FilledTonalButton(
                    content=ft.Text("Verify Code"),
                    ref=verify_btn,
                    icon=ft.Icons.VERIFIED_ROUNDED,
                    visible=False,
                    on_click=lambda e: page.run_task(_submit_code),
                ),
                # Status
                ft.Text(
                    ref=auth_status_text,
                    value="",
                    size=tokens.FONT_SM,
                    color=AppColors.SUCCESS,
                    text_align=ft.TextAlign.CENTER,
                    visible=False,
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

    # ── Page Controller & Update ──
    def _build_slide(index):
        if index == 0:
            return _build_page_1()
        elif index == 1:
            return _build_page_2()
        else:
            return _build_page_3()

    def _build_indicators():
        dots = []
        for i in range(3):
            dots.append(
                ft.Container(
                    width=10 if i == current_page["index"] else 6,
                    height=6,
                    border_radius=3,
                    bgcolor=ft.Colors.PRIMARY
                    if i == current_page["index"]
                    else ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE),
                )
            )
        return dots

    async def _on_get_started(e):
        state.onboarding_done = True
        await storage.set(constants.STORAGE_ONBOARDING_DONE, "true")
        if on_complete:
            on_complete()

    def _update_view():
        idx = current_page["index"]
        if slide_container.current:
            slide_container.current.content = _build_slide(idx)
        if indicator_row.current:
            indicator_row.current.controls = _build_indicators()
        if back_btn.current:
            back_btn.current.visible = idx > 0
        if next_btn.current:
            if idx == 2:
                next_btn.current.content = ft.Text("Get Started")
                next_btn.current.on_click = lambda e: page.run_task(_on_get_started, e)
                next_btn.current.disabled = not state.is_authenticated
            else:
                next_btn.current.content = ft.Text("Next")
                next_btn.current.on_click = _on_next
                next_btn.current.disabled = False
        page.update()

    def _on_next(e):
        if current_page["index"] < 2:
            current_page["index"] += 1
            _update_view()

    def _on_back(e):
        if current_page["index"] > 0:
            current_page["index"] -= 1
            _update_view()

    def _on_swipe(e: ft.DragEndEvent):
        if e.primary_velocity is not None:
            if e.primary_velocity < -200:  # Swipe left → next
                _on_next(e)
            elif e.primary_velocity > 200:  # Swipe right → back
                _on_back(e)

    # ── Structure ──
    nav_row = ft.Container(
        content=ft.Row(
            controls=[
                ft.TextButton(
                    content=ft.Text("Back"),
                    ref=back_btn,
                    on_click=_on_back,
                    visible=False,
                ),
                ft.Row(
                    ref=indicator_row,
                    controls=_build_indicators(),
                    spacing=tokens.SPACE_SM,
                ),
                ft.FilledButton(
                    content=ft.Text("Next"),
                    ref=next_btn,
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

    slide_content_container = ft.GestureDetector(
        content=ft.Container(
            ref=slide_container,
            content=_build_slide(0),
            expand=True,
            padding=ft.Padding(tokens.SPACE_XL, 0, tokens.SPACE_XL, 0),
        ),
        on_horizontal_drag_end=_on_swipe,
    )

    return ft.View(
        route="/onboarding",
        controls=[
            ft.SafeArea(
                content=ft.Column(
                    controls=[slide_content_container, nav_row],
                    expand=True,
                    spacing=0,
                ),
                expand=True,
            )
        ],
        padding=0,
    )
