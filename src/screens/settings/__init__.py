"""SettingsScreen — React-like, reads state and services from context."""

from __future__ import annotations

import flet as ft

from components.brand_header import build_brand_header
from core import constants, tokens
from core.storage_patch import MemoryLogHandler, resolve_storage_dir
from core.styles import glass_card, section_header, tip_text
from core.theme import AppColors
from state import AppStateCtx, ServiceCtx

# ── Logs dialog (no state needed — reads logs imperatively on open) ───────────


def _build_logs_dialog() -> ft.AlertDialog:
    page = ft.context.page
    import os

    memory_logs = MemoryLogHandler.get_logs()
    if memory_logs:
        log_text = "\n".join(memory_logs)
    else:
        log_file = os.path.join(resolve_storage_dir(), "colab.log")
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    log_text = "".join(f.readlines()[-200:])
            except Exception:
                log_text = "Could not read log file."
        else:
            log_text = "No activity logs recorded yet."

    log_control = ft.Text(
        value=log_text,
        size=tokens.FONT_XS,
        font_family="RobotoMono",
        color=AppColors.TERMINAL_GREEN,
        selectable=True,
    )

    async def _copy(e):
        try:
            await ft.Clipboard().set(log_control.value)
            page.snack_bar = ft.SnackBar(
                ft.Text("Logs copied to clipboard"), bgcolor=AppColors.SUCCESS
            )
            page.snack_bar.open = True
            page.update()
        except Exception:
            pass

    return ft.AlertDialog(
        modal=True,
        title=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.TERMINAL_ROUNDED,
                    size=tokens.ICON_MD,
                    color=ft.Colors.PRIMARY,
                ),
                ft.Text(
                    "Activity Terminal", size=tokens.FONT_LG, weight=ft.FontWeight.BOLD
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        content=ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        "Real-time log of sessions, websocket activity, and connection events.",
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Container(
                        content=ft.Column(
                            controls=[log_control],
                            scroll=ft.ScrollMode.AUTO,
                            expand=True,
                        ),
                        padding=tokens.SPACE_MD,
                        bgcolor=AppColors.LOG_TERMINAL_BG,
                        border=ft.Border.all(
                            1, ft.Colors.with_opacity(0.15, ft.Colors.WHITE)
                        ),
                        border_radius=tokens.RADIUS_SM,
                        expand=True,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            ),
            width=400,
            height=480,
        ),
        actions=[
            ft.IconButton(
                icon=ft.Icons.COPY_ROUNDED,
                tooltip="Copy logs",
                on_click=lambda e: page.run_task(_copy, e),
            ),
            ft.TextButton("Close", on_click=lambda e: page.pop_dialog()),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


# ── Settings screen ───────────────────────────────────────────────────────────


@ft.component
def SettingsScreen() -> ft.Control:
    """Full settings screen with all sections. Reads state from context."""
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    page = ft.context.page

    # ── Behavior section handlers ─────────────────────────────────────────────
    async def _on_keep_alive_change(e):
        state.keep_alive_enabled = e.control.value
        await services.storage.set(
            constants.STORAGE_KEEP_ALIVE, str(e.control.value).lower()
        )

    async def _on_keep_alive_disconnect_change(e):
        state.keep_alive_on_disconnect = e.control.value
        await services.storage.set(
            constants.STORAGE_KEEP_ALIVE_ON_DISCONNECT, str(e.control.value).lower()
        )

    async def _on_drive_path_change(e):
        state.drive_mount_path = e.control.value
        await services.storage.set(
            constants.STORAGE_DRIVE_MOUNT_PATH, state.drive_mount_path
        )

    # ── Auth section handlers ─────────────────────────────────────────────────
    async def _sign_out(e):
        try:
            await services.colab.revoke_auth()
        except Exception:
            pass
        state.is_authenticated = False
        state.auth_email = ""
        state.onboarding_done = False

    # ── Hardware section handlers ─────────────────────────────────────────────
    async def _on_gpu_change(e):
        state.default_gpu = e.control.value or ""
        await services.storage.set(constants.STORAGE_DEFAULT_GPU, state.default_gpu)

    async def _on_tpu_change(e):
        state.default_tpu = e.control.value or ""
        await services.storage.set(constants.STORAGE_DEFAULT_TPU, state.default_tpu)

    async def _on_timeout_change(e):
        try:
            val = int(e.control.value)
            state.default_timeout = val
            await services.storage.set(constants.STORAGE_DEFAULT_TIMEOUT, str(val))
        except (ValueError, TypeError):
            pass

    # ── Advanced / logs ───────────────────────────────────────────────────────
    async def _on_logtostderr_change(e):
        state.logtostderr = e.control.value
        await services.storage.set(
            constants.STORAGE_LOGTOSTDERR, str(e.control.value).lower()
        )

    # ── Theme ─────────────────────────────────────────────────────────────────
    def _make_theme_btn(label: str, mode: ft.ThemeMode) -> ft.Control:
        is_sel = state.theme_mode == mode

        def _select(e, m=mode):
            page.theme_mode = m
            state.theme_mode = m
            page.run_task(services.storage.set, constants.STORAGE_THEME, label.lower())
            page.update()

        btn = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.LIGHT_MODE_ROUNDED
                        if label == "Light"
                        else ft.Icons.DARK_MODE_ROUNDED
                        if label == "Dark"
                        else ft.Icons.BRIGHTNESS_AUTO_ROUNDED,
                        color=ft.Colors.PRIMARY
                        if is_sel
                        else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        label,
                        size=tokens.FONT_XS,
                        color=ft.Colors.PRIMARY if is_sel else ft.Colors.ON_SURFACE,
                        weight=ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=tokens.SPACE_XXS,
            ),
            expand=True,
            padding=ft.Padding(
                tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD
            ),
            border_radius=tokens.RADIUS_MD,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY)
            if is_sel
            else ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
            on_click=_select,
            ink=True,
        )
        return btn

    # ── GPU options ───────────────────────────────────────────────────────────
    GPU_OPTIONS = [
        ft.dropdown.Option("", "None"),
        ft.dropdown.Option("T4", "T4"),
        ft.dropdown.Option("A100", "A100"),
        ft.dropdown.Option("L4", "L4"),
        ft.dropdown.Option("TPU_V2", "TPU v2"),
    ]
    TPU_OPTIONS = [
        ft.dropdown.Option("", "None"),
        ft.dropdown.Option("TPU_V2", "TPU v2"),
        ft.dropdown.Option("TPU_V3", "TPU v3"),
    ]

    # ── Build sections ────────────────────────────────────────────────────────
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
                                            "Keep Alive on Disconnect",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Keep sessions running when the app closes"
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Switch(
                                    value=state.keep_alive_on_disconnect,
                                    on_change=lambda e: page.run_task(
                                        _on_keep_alive_disconnect_change, e
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

    hardware_section = ft.Column(
        controls=[
            section_header("HARDWARE DEFAULTS"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Dropdown(
                            label="Default GPU",
                            options=GPU_OPTIONS,
                            value=state.default_gpu or "",
                            border_radius=tokens.RADIUS_MD,
                            on_change=lambda e: page.run_task(_on_gpu_change, e),
                        ),
                        tip_text("Default GPU accelerator for new sessions"),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.Dropdown(
                            label="Default TPU",
                            options=TPU_OPTIONS,
                            value=state.default_tpu or "",
                            border_radius=tokens.RADIUS_MD,
                            on_change=lambda e: page.run_task(_on_tpu_change, e),
                        ),
                        tip_text("Default TPU accelerator for new sessions"),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.TextField(
                            label="Execution Timeout (seconds)",
                            value=str(state.default_timeout),
                            prefix_icon=ft.Icons.TIMER_ROUNDED,
                            keyboard_type=ft.KeyboardType.NUMBER,
                            border_radius=tokens.RADIUS_MD,
                            text_size=tokens.FONT_SM,
                            on_blur=lambda e: page.run_task(_on_timeout_change, e),
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

    preferences_section = ft.Column(
        controls=[
            section_header("PREFERENCES"),
            glass_card(
                ft.Column(
                    controls=[
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
                        ft.Row(
                            controls=[
                                _make_theme_btn("Light", ft.ThemeMode.LIGHT),
                                _make_theme_btn("Dark", ft.ThemeMode.DARK),
                                _make_theme_btn("System", ft.ThemeMode.SYSTEM),
                            ],
                            spacing=tokens.SPACE_SM,
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

    auth_section = ft.Column(
        controls=[
            section_header("ACCOUNT"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.ACCOUNT_CIRCLE_ROUNDED,
                                    size=tokens.ICON_XL,
                                    color=ft.Colors.PRIMARY,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            state.auth_email or "Not signed in",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        ft.Text(
                                            "Google Account"
                                            if state.is_authenticated
                                            else "Sign in to use Colab",
                                            size=tokens.FONT_XS,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                            ],
                            spacing=tokens.SPACE_MD,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.OutlinedButton(
                            "Sign Out",
                            icon=ft.Icons.LOGOUT_ROUNDED,
                            on_click=lambda e: page.run_task(_sign_out, e),
                            visible=state.is_authenticated,
                            style=ft.ButtonStyle(color=ft.Colors.ERROR),
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

    logs_section = ft.Column(
        controls=[
            section_header("TROUBLESHOOTING & LOGS"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Text(
                            "Live Activity Terminal",
                            size=tokens.FONT_MD,
                            weight=ft.FontWeight.W_500,
                        ),
                        ft.Text(
                            "View real-time connection activity, session logs, and diagnostic errors.",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Container(height=tokens.SPACE_XS),
                        ft.FilledButton(
                            "Open Terminal",
                            icon=ft.Icons.TERMINAL_ROUNDED,
                            on_click=lambda e: page.show_dialog(_build_logs_dialog()),
                        ),
                    ],
                    spacing=tokens.SPACE_XS,
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )

    about_section = ft.Column(
        controls=[
            section_header("ABOUT"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Container(
                            content=build_brand_header(
                                show_tagline=True, spacing_below=False
                            ),
                            opacity=0.8,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.Row(
                            controls=[
                                ft.Text("Core Engine", size=tokens.FONT_SM),
                                ft.Text(
                                    "google-colab-cli",
                                    size=tokens.FONT_SM,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Text(
                            "Disclaimer: Unofficial client application. Not affiliated with, authorized, sponsored, or endorsed by Google LLC.",
                            size=tokens.FONT_XXS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            italic=True,
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

    return ft.Column(
        controls=[
            build_brand_header(),
            behavior_section,
            hardware_section,
            preferences_section,
            auth_section,
            advanced_section,
            logs_section,
            about_section,
            ft.Container(height=tokens.SPACE_XXL),
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
