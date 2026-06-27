"""Onboarding view — 3-page welcome flow with OAuth sign-in."""

import flet as ft

from core import tokens, constants
from core.theme import AppColors


def build_onboarding_view(
    page: ft.Page,
    colab_service,
    state,
    storage,
    on_complete=None,
):
    """Build the 3-page onboarding view.

    Page 1: Welcome + feature highlights
    Page 2: What you can do
    Page 3: Sign in to Google (OAuth2 flow)
    """
    current_page = ft.Ref[int]()
    auth_code_field = ft.Ref[ft.TextField]()
    auth_status_text = ft.Ref[ft.Text]()
    auth_url_text = ft.Ref[ft.Text]()
    sign_in_btn = ft.Ref[ft.FilledButton]()
    get_started_btn = ft.Ref[ft.FilledButton]()
    page_indicator = ft.Ref[ft.Row]()

    def _feature_row(icon, title, subtitle):
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(icon, size=tokens.ICON_XL, color=ft.Colors.PRIMARY),
                        width=56,
                        height=56,
                        border_radius=tokens.RADIUS_MD,
                        bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(title, size=tokens.FONT_LG, weight=ft.FontWeight.W_600),
                            ft.Text(subtitle, size=tokens.FONT_SM, color=ft.Colors.ON_SURFACE_VARIANT),
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

    # ── Page 1: Welcome ──
    page1 = ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(height=tokens.SPACE_XXXL),
                ft.Icon(ft.Icons.CLOUD_ROUNDED, size=80, color=ft.Colors.PRIMARY),
                ft.Text(
                    constants.APP_NAME,
                    size=tokens.FONT_HERO,
                    weight=ft.FontWeight.W_800,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Cloud GPUs from your phone",
                    size=tokens.FONT_LG,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=tokens.SPACE_XXL),
                _feature_row(
                    ft.Icons.PLAY_ARROW_ROUNDED,
                    "Execute Python",
                    "Run code on cloud GPUs — T4, A100, H100",
                ),
                _feature_row(
                    ft.Icons.FOLDER_ROUNDED,
                    "Manage Files",
                    "Upload, download, and browse remote files",
                ),
                _feature_row(
                    ft.Icons.HISTORY_ROUNDED,
                    "Session History",
                    "Export logs as notebooks, markdown, or JSONL",
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(tokens.SPACE_XL, 0, tokens.SPACE_XL, 0),
    )

    # ── Page 2: How it works ──
    page2 = ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(height=tokens.SPACE_XXXL),
                ft.Icon(ft.Icons.ROCKET_LAUNCH_ROUNDED, size=80, color=ft.Colors.PRIMARY),
                ft.Text(
                    "How it works",
                    size=tokens.FONT_XXL,
                    weight=ft.FontWeight.W_700,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=tokens.SPACE_LG),
                _feature_row(
                    ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED,
                    "1. Create a session",
                    "Choose CPU (free), T4 GPU, or TPU. Sessions auto-terminate after 24h.",
                ),
                _feature_row(
                    ft.Icons.CODE_ROUNDED,
                    "2. Write & run code",
                    "Type Python in the terminal or pick a .py / .ipynb file.",
                ),
                _feature_row(
                    ft.Icons.CLOUD_UPLOAD_ROUNDED,
                    "3. Transfer files",
                    "Upload data to /content, download results back.",
                ),
                _feature_row(
                    ft.Icons.STOP_CIRCLE_OUTLINED,
                    "4. Stop when done",
                    "Stop the session to free resources. Or let it auto-stop.",
                ),
                ft.Container(height=tokens.SPACE_MD),
                ft.Container(
                    content=ft.Text(
                        "💡 CPU sessions are always free. GPU/TPU have usage limits on the free tier.",
                        size=tokens.FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    padding=ft.Padding(tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD),
                    bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
                    border_radius=tokens.RADIUS_MD,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(tokens.SPACE_XL, 0, tokens.SPACE_XL, 0),
    )

    # ── Page 3: Sign In ──
    page3 = ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(height=tokens.SPACE_XXXL),
                ft.Icon(ft.Icons.LOCK_OPEN_ROUNDED, size=80, color=ft.Colors.PRIMARY),
                ft.Text(
                    "Sign in to Google",
                    size=tokens.FONT_XXL,
                    weight=ft.FontWeight.W_700,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Required to create and manage Colab sessions",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=tokens.SPACE_LG),
                # CLI version info
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.CHECK_CIRCLE_ROUNDED,
                                size=tokens.ICON_MD,
                                color=AppColors.SUCCESS,
                            ),
                            ft.Text(
                                f"Colab CLI v{state.cli_version}" if state.cli_version else "Colab CLI ready",
                                size=tokens.FONT_SM,
                            ),
                        ],
                        spacing=tokens.SPACE_SM,
                    ),
                    padding=ft.Padding(tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD),
                    bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
                    border_radius=tokens.RADIUS_MD,
                ),
                ft.Container(height=tokens.SPACE_LG),
                # Sign in button
                ft.FilledButton(
                    ref=sign_in_btn,
                    text=constants.LBL_SIGN_IN,
                    icon=ft.Icons.LOGIN_ROUNDED,
                    width=float("inf"),
                    style=ft.ButtonStyle(
                        padding=ft.Padding(tokens.SPACE_XL, tokens.SPACE_MD, tokens.SPACE_XL, tokens.SPACE_MD),
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
                    text="Verify Code",
                    icon=ft.Icons.VERIFIED_ROUNDED,
                    visible=False,
                    on_click=lambda e: page.run_task(_submit_code),
                    data="verify_btn",
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
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(tokens.SPACE_XL, 0, tokens.SPACE_XL, 0),
    )

    async def _start_auth():
        try:
            sign_in_btn.current.disabled = True
            sign_in_btn.current.text = "Generating link..."
            page.update()

            url = await colab_service.get_auth_url()
            # Open in browser
            await page.launch_url_async(url)

            # Show the code entry fields
            if auth_url_text.current:
                auth_url_text.current.value = "A browser window opened. Sign in, then paste the authorization code below."
                auth_url_text.current.visible = True
            if auth_code_field.current:
                auth_code_field.current.visible = True

            # Show verify button
            for c in page3.content.controls:
                if hasattr(c, 'data') and c.data == "verify_btn":
                    c.visible = True

            sign_in_btn.current.text = "Link opened in browser"
            page.update()
        except Exception as e:
            sign_in_btn.current.disabled = False
            sign_in_btn.current.text = constants.LBL_SIGN_IN
            if auth_status_text.current:
                auth_status_text.current.value = f"Error: {e}"
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
            if get_started_btn.current:
                get_started_btn.current.disabled = False
        else:
            if auth_status_text.current:
                auth_status_text.current.value = f"❌ {result['error']}"
                auth_status_text.current.color = AppColors.ERROR
                auth_status_text.current.visible = True
        page.update()

    # ── Page container with swipe ──
    pages_container = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        tabs=[
            ft.Tab(content=page1),
            ft.Tab(content=page2),
            ft.Tab(content=page3),
        ],
        label_visibility=False,
        divider_height=0,
        expand=True,
    )

    # Navigation buttons
    def _on_next(e):
        idx = pages_container.selected_index
        if idx < 2:
            pages_container.selected_index = idx + 1
            page.update()

    def _on_back(e):
        idx = pages_container.selected_index
        if idx > 0:
            pages_container.selected_index = idx - 1
            page.update()

    async def _on_get_started(e):
        await storage.set(constants.STORAGE_ONBOARDING_DONE, True)
        if on_complete:
            on_complete()

    nav_row = ft.Container(
        content=ft.Row(
            controls=[
                ft.TextButton(
                    text="Back",
                    on_click=_on_back,
                ),
                ft.Row(
                    controls=[
                        ft.Container(width=8, height=8, border_radius=4, bgcolor=ft.Colors.PRIMARY),
                        ft.Container(width=8, height=8, border_radius=4, bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE)),
                        ft.Container(width=8, height=8, border_radius=4, bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE)),
                    ],
                    spacing=tokens.SPACE_SM,
                    ref=page_indicator,
                ),
                ft.FilledButton(
                    ref=get_started_btn,
                    text="Next",
                    on_click=_on_next,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_XL),
    )

    def _on_tab_change(e):
        idx = pages_container.selected_index
        if page_indicator.current:
            for i, dot in enumerate(page_indicator.current.controls):
                dot.bgcolor = ft.Colors.PRIMARY if i == idx else ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE)

        if get_started_btn.current:
            if idx == 2:
                get_started_btn.current.text = "Get Started"
                get_started_btn.current.on_click = lambda e: page.run_task(_on_get_started, e)
                get_started_btn.current.disabled = not state.is_authenticated
            else:
                get_started_btn.current.text = "Next"
                get_started_btn.current.on_click = _on_next
                get_started_btn.current.disabled = False
        page.update()

    pages_container.on_change = _on_tab_change

    return ft.Column(
        controls=[pages_container, nav_row],
        expand=True,
        spacing=0,
    )
