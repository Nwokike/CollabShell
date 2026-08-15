"""SettingsScreen — React-like, reads state and services from context."""

from __future__ import annotations

import flet as ft

from core import tokens
from core.styles import build_banner_ad
from screens.settings.about_section import build_about_section
from screens.settings.account_section import build_account_section
from screens.settings.advanced_section import build_advanced_section
from screens.settings.behavior_section import build_behavior_section
from screens.settings.execution_section import build_execution_section
from screens.settings.hardware_section import build_hardware_section
from screens.settings.logs_section import build_logs_section
from screens.settings.preferences_section import build_preferences_section
from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx


@ft.component
def SettingsScreen() -> ft.Control:
    """Full settings screen with modular cards reading directly from context."""
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    return ft.Column(
        controls=[
            build_preferences_section(page, state, services),
            build_account_section(page, state, services, snack=controller.show_snack),
            build_banner_ad(page),
            build_hardware_section(page, state, services),
            build_execution_section(page, state, services),
            build_behavior_section(page, state, services),
            build_banner_ad(page),
            build_advanced_section(page, state, services),
            build_logs_section(page, state, services),
            build_about_section(page, state, services),
            ft.Container(height=tokens.SPACE_XXL),
        ],
        spacing=tokens.SPACE_SM,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


__all__ = ["SettingsScreen"]
