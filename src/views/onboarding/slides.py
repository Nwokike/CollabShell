import flet as ft

from components.brand_header import build_brand_header
from core import constants, tokens
from core.theme import AppColors


def feature_row(icon, title, subtitle):
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, size=tokens.ICON_XL, color=ft.Colors.PRIMARY),
                    width=tokens.CARD_ICON_CONTAINER,
                    height=tokens.CARD_ICON_CONTAINER,
                    border_radius=tokens.RADIUS_MD,
                    bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[
                        ft.Text(title, size=tokens.FONT_LG, weight=ft.FontWeight.W_600),
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


def build_page_1():
    return ft.Column(
        controls=[
            build_brand_header(),
            ft.Container(height=tokens.SPACE_MD),
            feature_row(
                ft.Icons.CODE_ROUNDED,
                "Interactive Notebook",
                "Write, organize, and execute code cells with real-time output",
            ),
            feature_row(
                ft.Icons.TERMINAL_ROUNDED,
                "Real PTY Terminal",
                "Access a raw, interactive Linux bash shell for your runtime environment",
            ),
            feature_row(
                ft.Icons.FOLDER_ROUNDED,
                "Cloud File Explorer",
                "Upload, download, and manage remote workspace files and folders",
            ),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=tokens.SPACE_SM,
    )


def build_page_2():
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
            feature_row(
                ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED,
                "1. Connect Session",
                "Start CPU (free), GPU (T4/A100/H100), or TPU session runtimes.",
            ),
            feature_row(
                ft.Icons.NOTE_ADD_ROUNDED,
                "2. Run Cells",
                "Edit and run interactive code blocks in the notebook view.",
            ),
            feature_row(
                ft.Icons.TERMINAL_ROUNDED,
                "3. Run Shell Commands",
                "Execute bash scripts, clone git repos, or run interactive CLIs in terminal.",
            ),
            feature_row(
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


def build_page_3(
    sign_in_btn,
    auth_url_text,
    auth_code_field,
    verify_btn,
    auth_status_text,
    start_auth_task,
    submit_code_task,
):
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
                on_click=start_auth_task,
            ),
            ft.Text(
                ref=auth_url_text,
                value="",
                size=tokens.FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align=ft.TextAlign.CENTER,
                selectable=True,
                visible=False,
            ),
            ft.TextField(
                ref=auth_code_field,
                label="Paste authorization code",
                prefix_icon=ft.Icons.KEY_ROUNDED,
                border_radius=tokens.RADIUS_MD,
                text_size=tokens.FONT_MD,
                visible=False,
                on_submit=submit_code_task,
            ),
            ft.FilledTonalButton(
                content=ft.Text("Verify Code"),
                ref=verify_btn,
                icon=ft.Icons.VERIFIED_ROUNDED,
                visible=False,
                on_click=submit_code_task,
            ),
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
