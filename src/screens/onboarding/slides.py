"""Onboarding presentation slides."""

from __future__ import annotations

import flet as ft

from components.brand_header import build_brand_header
from core import tokens


def feature_row(icon, title, subtitle):
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, size=tokens.ICON_MD, color=ft.Colors.PRIMARY),
                    width=tokens.AVATAR_MD,
                    height=tokens.AVATAR_MD,
                    border_radius=tokens.RADIUS_MD,
                    bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[
                        ft.Text(title, size=tokens.FONT_MD, weight=ft.FontWeight.W_600),
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
