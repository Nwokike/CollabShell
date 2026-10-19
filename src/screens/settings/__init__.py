"""SettingsScreen — React-like, matching original layout and section arrangements."""

from __future__ import annotations

import logging

import flet as ft

from core import tokens
from core.styles import build_banner_ad
from screens.settings.about_section import build_about_section
from screens.settings.account_section import build_account_section
from screens.settings.advanced_section import build_advanced_section
from screens.settings.ai_section import build_ai_section
from screens.settings.behavior_section import build_behavior_section
from screens.settings.data_section import build_data_section
from screens.settings.execution_section import build_execution_section
from screens.settings.hardware_section import build_hardware_section
from screens.settings.logs_section import build_logs_section
from screens.settings.preferences_section import build_preferences_section
from screens.settings.premium_section import build_premium_section
from state import AppStateCtx, ServiceCtx

logger = logging.getLogger("Settings")


@ft.component
def SettingsScreen() -> ft.Control:
    """Full settings screen with modular cards arranged 1:1 with original app."""
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    page = ft.context.page

    # Each section is built in isolation so one broken card cannot blank the
    # whole screen — and so the traceback names the section instead of leaving
    # the user with an empty column and no idea why. Every entry takes the
    # same (page, state, services) triple; the banner builder takes fewer, so
    # it is wrapped to match rather than called bare.
    sections = (
        build_preferences_section,
        build_account_section,
        lambda page, state, services, defer=None: build_banner_ad(page),
        build_ai_section,
        build_premium_section,
        build_hardware_section,
        build_execution_section,
        build_behavior_section,
        lambda page, state, services, defer=None: build_banner_ad(page),
        build_advanced_section,
        build_logs_section,
        build_data_section,
        build_about_section,
    )

    # Work that must happen AFTER the component has patched — the section
    # loaders. It is collected here and run from ONE effect, because
    # `SettingsScreen` is a real component and can register a hook safely.
    #
    # It must NOT be registered from inside a section builder: those are plain
    # functions, and flet's `use_effect` needs a component render frame
    # (`current_component()`), not merely a bound renderer. Where the frame is
    # missing, `use_effect` raises — and that raise escapes
    # `Component.update()` into the session's update loop
    # (`flet/messaging/session.py:719-720`), which has no exception handler:
    # the scheduler task dies, every later update is silently dropped, and the
    # screen never changes. That was the blank Settings tab.
    #
    # One effect, registered here, always — so the hook count cannot shift
    # between renders and misalign the hook cursor.
    pending: list = []

    controls: list[ft.Control] = []
    for build in sections:
        try:
            controls.append(build(page, state, services, pending.append))
        except Exception as ex:
            logger.exception("Settings section failed: %r", build)
            controls.append(
                ft.Container(
                    content=ft.Text(
                        "This section could not be shown. "
                        f"{type(ex).__name__}: {ex}",
                        size=tokens.FONT_SM,
                        color=ft.Colors.ERROR,
                    ),
                    padding=tokens.SPACE_MD,
                )
            )

    def _run_pending():
        """Run the collected section work, after the patch has been emitted."""
        for work in pending:
            try:
                work()
            except Exception:
                logger.exception("Settings deferred work failed")

    # Exactly one effect, always — so the hook cursor cannot shift between
    # renders and bind an effect to the wrong slot.
    ft.use_effect(_run_pending, [])

    return ft.Column(
        controls=[
            *controls,
            ft.Container(height=tokens.SPACE_XXL),
        ],
        spacing=tokens.SPACE_SM,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


__all__ = ["SettingsScreen"]
