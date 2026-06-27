"""Settings view — every CLI option exposed, following Sherlock's pattern exactly."""

from __future__ import annotations

import flet as ft

from core import tokens, constants
from core.styles import (
    section_header,
    setting_tile,
    glass_card,
    build_banner_ad,
    tip_text,
)
from core.theme import AppColors


def build_settings_view(
    page: ft.Page,
    colab_service,
    state,
    storage,
    on_theme_change=None,
) -> ft.View:
    """Build the settings view with every CLI flag exposed."""

    def _snack(msg: str):
        page.snack_bar = ft.SnackBar(content=ft.Text(msg))
        page.snack_bar.open = True
        page.update()

    # ── PREFERENCES ───────────────────────────────────────────────────────────
    theme_mode_state = ["system"]
    if state.theme_mode == ft.ThemeMode.LIGHT:
        theme_mode_state[0] = "light"
    elif state.theme_mode == ft.ThemeMode.DARK:
        theme_mode_state[0] = "dark"

    def create_theme_card(mode: str, label: str, icon: str):
        is_sel = theme_mode_state[0] == mode
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        icon,
                        color=ft.Colors.PRIMARY
                        if is_sel
                        else ft.Colors.ON_SURFACE_VARIANT,
                        size=16,
                    ),
                    ft.Text(
                        label,
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL,
                        color=ft.Colors.PRIMARY if is_sel else ft.Colors.ON_SURFACE,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
            ),
            padding=ft.Padding(8, 10, 8, 10),
            border_radius=tokens.RADIUS_MD,
            border=ft.Border.all(2, ft.Colors.PRIMARY)
            if is_sel
            else ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY)
            if is_sel
            else ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
            expand=True,
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
            on_click=lambda e: page.run_task(change_theme_and_update, mode),
        )

    light_btn = create_theme_card("light", "Light", ft.Icons.LIGHT_MODE_ROUNDED)
    dark_btn = create_theme_card("dark", "Dark", ft.Icons.DARK_MODE_ROUNDED)
    system_btn = create_theme_card(
        "system", "System", ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED
    )

    async def change_theme_and_update(mode_str):
        theme_mode_state[0] = mode_str
        if mode_str == "system":
            state.theme_mode = ft.ThemeMode.SYSTEM
        elif mode_str == "light":
            state.theme_mode = ft.ThemeMode.LIGHT
        else:
            state.theme_mode = ft.ThemeMode.DARK

        page.theme_mode = state.theme_mode
        await storage.set(constants.STORAGE_THEME, mode_str)
        if on_theme_change:
            on_theme_change()

        # Update button borders/colors
        for m, btn in [
            ("light", light_btn),
            ("dark", dark_btn),
            ("system", system_btn),
        ]:
            is_sel = m == mode_str
            btn.border = (
                ft.Border.all(2, ft.Colors.PRIMARY)
                if is_sel
                else ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE))
            )
            btn.bgcolor = (
                ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY)
                if is_sel
                else ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE)
            )
            btn.content.controls[0].color = (
                ft.Colors.PRIMARY if is_sel else ft.Colors.ON_SURFACE_VARIANT
            )
            btn.content.controls[1].color = (
                ft.Colors.PRIMARY if is_sel else ft.Colors.ON_SURFACE
            )
            btn.content.controls[1].weight = (
                ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL
            )

        page.update()

    preferences_section = ft.Column(
        controls=[
            section_header("PREFERENCES"),
            glass_card(
                ft.Column(
                    controls=[
                        # Label Row
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.PALETTE_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Display Theme",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        ft.Text(
                                            "Appearance mode",
                                            size=tokens.FONT_XS,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Container(height=tokens.SPACE_SM),
                        # Selector Row
                        ft.Row(
                            [light_btn, dark_btn, system_btn],
                            spacing=8,
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )

    # ── AUTHENTICATION ────────────────────────────────────────────────────────
    async def _on_auth_method_change(e):
        val = e.control.value
        state.auth_method = val
        await storage.set(constants.STORAGE_AUTH_METHOD, val)
        page.update()

    async def _on_reauth(e):
        _snack("Clearing token...")
        await colab_service.clear_token()
        state.is_authenticated = False
        state.auth_email = ""
        state.onboarding_done = False
        await storage.set(constants.STORAGE_ONBOARDING_DONE, "false")
        _snack("Token cleared. Redirecting to onboarding...")
        page.route = "/onboarding"
        page.update()

    async def _on_whoami(e):
        _snack("Checking credentials...")
        result = await colab_service.check_auth()
        if result["authenticated"]:
            msg = f"Email: {result['email']}\nExpires: {result['expires_in']}\nMethod: {result['auth_method']}"
        else:
            msg = "Not authenticated"

        info_dialog = ft.AlertDialog(
            title=ft.Text("Who Am I"),
            content=ft.Text(msg),
            actions=[ft.TextButton("OK", on_click=lambda e: page.pop_dialog())],
        )
        page.show_dialog(info_dialog)

    auth_status_color = AppColors.SUCCESS if state.is_authenticated else AppColors.ERROR
    auth_status_icon = (
        ft.Icons.CHECK_CIRCLE_ROUNDED
        if state.is_authenticated
        else ft.Icons.ERROR_ROUNDED
    )
    auth_status_text = (
        f"Signed in as {state.auth_email}"
        if state.is_authenticated
        else "Not signed in"
    )

    auth_section = ft.Column(
        controls=[
            section_header("AUTHENTICATION"),
            glass_card(
                ft.Column(
                    controls=[
                        # Auth status
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    auth_status_icon,
                                    size=tokens.ICON_LG,
                                    color=auth_status_color,
                                ),
                                ft.Text(
                                    auth_status_text,
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                    expand=True,
                                ),
                            ],
                            spacing=tokens.SPACE_MD,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        # Auth method
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.VPN_KEY_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Auth Method",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            constants.TIP_AUTH_OAUTH2
                                            if state.auth_method == "oauth2"
                                            else constants.TIP_AUTH_ADC
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Dropdown(
                                    value=state.auth_method,
                                    options=[
                                        ft.dropdown.Option("oauth2", "OAuth2"),
                                        ft.dropdown.Option("adc", "ADC"),
                                    ],
                                    width=110,
                                    border_radius=tokens.RADIUS_MD,
                                    text_size=tokens.FONT_SM,
                                    on_select=lambda e: page.run_task(
                                        _on_auth_method_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        # Re-authenticate
                        ft.Row(
                            controls=[
                                ft.OutlinedButton(
                                    constants.LBL_RE_AUTH,
                                    icon=ft.Icons.REFRESH_ROUNDED,
                                    on_click=lambda e: page.run_task(_on_reauth, e),
                                    expand=True,
                                ),
                                ft.OutlinedButton(
                                    "Who Am I",
                                    icon=ft.Icons.PERSON_SEARCH_ROUNDED,
                                    on_click=lambda e: page.run_task(_on_whoami, e),
                                    expand=True,
                                ),
                            ],
                            spacing=tokens.SPACE_SM,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )

    # ── HARDWARE DEFAULTS ─────────────────────────────────────────────────────
    async def _on_gpu_default(e):
        state.default_gpu = e.control.value or ""
        await storage.set(constants.STORAGE_DEFAULT_GPU, state.default_gpu)

    async def _on_tpu_default(e):
        state.default_tpu = e.control.value or ""
        await storage.set(constants.STORAGE_DEFAULT_TPU, state.default_tpu)

    hardware_section = ft.Column(
        controls=[
            section_header("HARDWARE DEFAULTS"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.DEVELOPER_BOARD_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Default GPU",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Pre-selected GPU when creating new sessions"
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Dropdown(
                                    value=state.default_gpu or "",
                                    options=[
                                        ft.dropdown.Option("", "None (CPU)"),
                                        ft.dropdown.Option("T4", "T4 · Free"),
                                        ft.dropdown.Option("L4", "L4 · Pro"),
                                        ft.dropdown.Option("G4", "G4 · Pro"),
                                        ft.dropdown.Option("A100", "A100 · Pro+"),
                                        ft.dropdown.Option("H100", "H100 · Pro+"),
                                    ],
                                    width=130,
                                    border_radius=tokens.RADIUS_MD,
                                    text_size=tokens.FONT_SM,
                                    on_select=lambda e: page.run_task(
                                        _on_gpu_default, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.BOLT_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Default TPU",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Pre-selected TPU when creating new sessions"
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Dropdown(
                                    value=state.default_tpu or "",
                                    options=[
                                        ft.dropdown.Option("", "None"),
                                        ft.dropdown.Option("v5e1", "v5e1 · Free"),
                                        ft.dropdown.Option("v6e1", "v6e1 · Free"),
                                    ],
                                    width=130,
                                    border_radius=tokens.RADIUS_MD,
                                    text_size=tokens.FONT_SM,
                                    on_select=lambda e: page.run_task(
                                        _on_tpu_default, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                    ],
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )

    # ── EXECUTION ─────────────────────────────────────────────────────────────
    async def _on_timeout_change(e):
        state.default_timeout = int(e.control.value)
        await storage.set(constants.STORAGE_DEFAULT_TIMEOUT, state.default_timeout)

    async def _on_log_format_change(e):
        state.default_log_format = e.control.value
        await storage.set(constants.STORAGE_LOG_FORMAT, state.default_log_format)

    execution_section = ft.Column(
        controls=[
            section_header("EXECUTION"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.TIMER_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Default Timeout",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(constants.TIP_TIMEOUT),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Dropdown(
                                    value=str(state.default_timeout),
                                    options=[
                                        ft.dropdown.Option(str(t), f"{t}s")
                                        for t in constants.TIMEOUT_OPTIONS
                                    ],
                                    width=100,
                                    border_radius=tokens.RADIUS_MD,
                                    text_size=tokens.FONT_SM,
                                    on_select=lambda e: page.run_task(
                                        _on_timeout_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.SAVE_ALT_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Log Export Format",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Default format when exporting session logs"
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Dropdown(
                                    value=state.default_log_format,
                                    options=[
                                        ft.dropdown.Option("ipynb", ".ipynb"),
                                        ft.dropdown.Option("md", ".md"),
                                        ft.dropdown.Option("jsonl", ".jsonl"),
                                        ft.dropdown.Option("txt", ".txt"),
                                    ],
                                    width=100,
                                    border_radius=tokens.RADIUS_MD,
                                    text_size=tokens.FONT_SM,
                                    on_select=lambda e: page.run_task(
                                        _on_log_format_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                    ],
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )

    # ── SESSION BEHAVIOR ──────────────────────────────────────────────────────
    async def _on_keep_alive_change(e):
        state.keep_alive_enabled = e.control.value
        await storage.set(constants.STORAGE_KEEP_ALIVE, state.keep_alive_enabled)

    async def _on_auto_stop_change(e):
        state.auto_stop_on_close = e.control.value
        await storage.set(constants.STORAGE_AUTO_STOP, state.auto_stop_on_close)

    async def _on_drive_path_change(e):
        state.drive_mount_path = e.control.value
        await storage.set(constants.STORAGE_DRIVE_MOUNT_PATH, state.drive_mount_path)

    behavior_section = ft.Column(
        controls=[
            section_header("SESSION BEHAVIOR"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Keep-Alive",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(constants.TIP_KEEP_ALIVE),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Switch(
                                    value=state.keep_alive_enabled,
                                    on_change=lambda e: page.run_task(
                                        _on_keep_alive_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.Row(
                            controls=[
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Auto-Stop on Close",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Stop all sessions when the app closes"
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Switch(
                                    value=state.auto_stop_on_close,
                                    on_change=lambda e: page.run_task(
                                        _on_auto_stop_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.TextField(
                            value=state.drive_mount_path,
                            label="Drive Mount Path",
                            prefix_icon=ft.Icons.ADD_TO_DRIVE_ROUNDED,
                            border_radius=tokens.RADIUS_MD,
                            text_size=tokens.FONT_SM,
                            on_blur=lambda e: page.run_task(_on_drive_path_change, e),
                        ),
                        tip_text(constants.TIP_DRIVE_MOUNT),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )

    # ── ADVANCED ──────────────────────────────────────────────────────────────
    async def _on_logtostderr_change(e):
        state.logtostderr = e.control.value
        await storage.set(constants.STORAGE_LOGTOSTDERR, state.logtostderr)

    advanced_section = ft.Column(
        controls=[
            section_header("ADVANCED"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Log to Stderr",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Debug: route all CLI output to stderr"
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Switch(
                                    value=state.logtostderr,
                                    on_change=lambda e: page.run_task(
                                        _on_logtostderr_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )

    # ── UPDATES ───────────────────────────────────────────────────────────────
    async def _on_check_updates(e):
        _snack("Checking for updates...")
        new_version = await colab_service.check_for_updates()
        if new_version:
            state.update_available_version = new_version
            _snack(f"Update available: v{new_version}")
        else:
            _snack("You're up to date!")

    updates_section = ft.Column(
        controls=[
            section_header("UPDATES"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.INFO_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "CLI Version",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        ft.Text(
                                            f"v{state.cli_version}"
                                            if state.cli_version
                                            else "Unknown",
                                            size=tokens.FONT_XS,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                            ],
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.Row(
                            controls=[
                                ft.OutlinedButton(
                                    constants.LBL_CHECK_UPDATES,
                                    icon=ft.Icons.SYSTEM_UPDATE_ROUNDED,
                                    on_click=lambda e: page.run_task(
                                        _on_check_updates, e
                                    ),
                                    expand=True,
                                ),
                                ft.OutlinedButton(
                                    constants.LBL_MANAGE_COMPUTE,
                                    icon=ft.Icons.CREDIT_CARD_ROUNDED,
                                    on_click=lambda e: page.run_task(
                                        ft.UrlLauncher().launch_url,
                                        "https://colab.research.google.com/signup",
                                    ),
                                    expand=True,
                                ),
                            ],
                            spacing=tokens.SPACE_SM,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )

    # ── ABOUT ─────────────────────────────────────────────────────────────────
    about_section = ft.Column(
        controls=[
            section_header("ABOUT"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Image(
                                    src="icon.png",
                                    width=48,
                                    height=48,
                                    fit=ft.BoxFit.CONTAIN,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            f"{constants.APP_NAME} v{constants.APP_VERSION}",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_600,
                                        ),
                                        ft.Text(
                                            "Cloud GPUs from your phone",
                                            size=tokens.FONT_XS,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                ),
                            ],
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        setting_tile(
                            icon=ft.Icons.CODE_ROUNDED,
                            title="Powered by google-colab-cli",
                            subtitle="github.com/googlecolab/google-colab-cli",
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )

    # ── Full view ─────────────────────────────────────────────────────────────
    view_content = ft.Column(
        controls=[
            preferences_section,
            auth_section,
            build_banner_ad(page),
            hardware_section,
            execution_section,
            behavior_section,
            advanced_section,
            build_banner_ad(page),
            updates_section,
            about_section,
            ft.Container(height=tokens.SPACE_XXL),
        ],
        spacing=tokens.SPACE_SM,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    return ft.View(
        route="/settings",
        controls=[view_content],
        padding=0,
    )
