"""SettingsScreen — React-like, reads state and services from context."""

from __future__ import annotations

import flet as ft

from components.brand_header import build_brand_header
from core import tokens
from screens.settings.about_section import build_about_section
from screens.settings.account_section import build_account_section
from screens.settings.advanced_section import build_advanced_section
from screens.settings.behavior_section import build_behavior_section
from screens.settings.hardware_section import build_hardware_section
from screens.settings.logs_section import build_logs_section
from screens.settings.preferences_section import build_preferences_section
from state import AppStateCtx, ServiceCtx


@ft.component
def SettingsScreen() -> ft.Control:
    """Full settings screen with modular cards reading directly from context."""
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    page = ft.context.page

    return ft.Column(
        controls=[
            build_brand_header(),
            build_behavior_section(page, state, services),
            build_hardware_section(page, state, services),
            build_preferences_section(page, state, services),
            build_account_section(page, state, services),
            build_advanced_section(page, state, services),
            build_logs_section(page, state, services),
            build_about_section(page, state, services),
            ft.Container(height=tokens.SPACE_XXL),
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


__all__ = ["SettingsScreen"]
