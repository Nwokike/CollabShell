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


def _section_error(label: str, ex: BaseException) -> ft.Control:
    """The card that replaces a section that could not be built.

    The user must be able to tell WHICH card failed and why, because the
    alternative — a section that silently does not appear — reads as "the
    setting does not exist" and sends them looking in the wrong place.
    """
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    label,
                    size=tokens.FONT_XS,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.ERROR,
                ),
                ft.Text(
                    f"This section could not be shown. {type(ex).__name__}: {ex}",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ERROR,
                ),
            ],
            spacing=tokens.SPACE_XS,
        ),
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM
        ),
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ERROR),
    )


@ft.component
def SettingsScreen() -> ft.Control:
    """Full settings screen with modular cards arranged 1:1 with original app."""
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    page = ft.context.page

    # Each section is built in isolation.
    #
    # A raise inside a section builder does NOT stay inside the section: it
    # unwinds through this component's body, through `Component.update()`, and
    # into the session's update loop (`flet/messaging/session.py:718-720`),
    # which has no exception handler around `control.update()`. The scheduler
    # task dies there, every later update is silently dropped, and the screen
    # stops changing — the tab switches, the content never follows, and
    # nothing is logged. That is the failure this guards against.
    #
    # Every builder here takes the same (page, state, services) triple. That
    # uniformity is deliberate: the last version of this loop added a fourth
    # `defer` parameter for deferred work but converted only four of the
    # thirteen builders to accept it, so the other nine raised
    # `TypeError: takes 3 positional arguments but 4 were given` and the screen
    # filled with error cards. A test now pins the arity.
    # The premium card is NOT BUILT on the Play channel — not even an empty
    # container. An external-checkout surface inside a Play-distributed build
    # is a policy violation, and "Assistant premium / Unavailable" was the
    # leak the owner found: both references state the rule as "not even a
    # disabled card — nothing to declare, nothing to reach, ads stay on"
    # (ktv-player `settings_screen.py:1229-1233`, DDGS `settings_screen:164`).
    from core.channel import CHANNEL

    sections: tuple[tuple[str, object], ...] = (
        ("APPEARANCE", build_preferences_section),
        ("AUTHENTICATION", build_account_section),
        ("SPONSOR", lambda page, state, services: build_banner_ad(page)),
        ("ASSISTANT", build_ai_section),
        *([] if CHANNEL == "play" else [("PREMIUM", build_premium_section)]),
        ("HARDWARE DEFAULTS", build_hardware_section),
        ("EXECUTION", build_execution_section),
        ("SESSION BEHAVIOR", build_behavior_section),
        ("SPONSOR", lambda page, state, services: build_banner_ad(page)),
        ("ADVANCED", build_advanced_section),
        ("TROUBLESHOOTING & LOGS", build_logs_section),
        ("DATA & STORAGE", build_data_section),
        ("ABOUT", build_about_section),
    )

    controls: list[ft.Control] = []
    for label, build in sections:
        try:
            controls.append(build(page, state, services))
        except Exception as ex:
            logger.exception("Settings section %r failed to build", label)
            controls.append(_section_error(label, ex))

    return ft.Column(
        controls=[*controls, ft.Container(height=tokens.SPACE_XXL)],
        spacing=tokens.SPACE_SM,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


__all__ = ["SettingsScreen"]
