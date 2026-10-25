"""Assistant settings section — thinking depth, router, model, credits.

Built with the same section_header/glass_card idiom as every other settings
section. Every row reads the live services through context so the numbers
cannot disagree with what the assistant actually charges.
"""

from __future__ import annotations

import logging

import flet as ft

from core import constants, tokens
from core.styles import glass_card, section_header, tip_text
from services import ai_credits

logger = logging.getLogger("AssistantSettings")


def _row(title: str, subtitle: str, trailing=None, icon=None) -> ft.Row:
    # Every row carries an icon that says what the row IS — a brain for
    # thinking, a memory chip for the model, a bolt for credits — so the
    # assistant card scans like every other settings card instead of one
    # repeated glyph. DDGS's card uses a distinct icon per row too
    # (sections_ai.py:149, 165, 197, 216).
    return ft.Row(
        controls=[
            ft.Icon(
                icon or tokens.ASSISTANT_ICON,
                size=tokens.ICON_LG,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Column(
                controls=[
                    ft.Text(
                        title,
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.W_500,
                    ),
                    tip_text(subtitle),
                ],
                spacing=tokens.SPACE_XXS,
                expand=True,
            ),
            *( [trailing] if trailing is not None else [] ),
        ],
        spacing=tokens.SPACE_LG,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _effective_router_url(state) -> str:
    """The URL the app is actually using: the override, or the router's port.

    Showing the live value means the field never lies — before this it showed a
    hardcoded 8082 that had nothing to do with where the router actually
    landed. An empty override shows the derived URL, so the default path is
    visible rather than looking like the field was never filled in.
    """
    override = str(getattr(state, "ai_router_url", "") or "").strip()
    if override:
        return override
    from services import router

    return router.current_url()


def _router_is_up(state) -> bool:
    """Whether the app believes a router is answering, without probing.

    The watchdog owns liveness (`services/router_watchdog`); this only reads
    what it published, so opening Settings costs no socket of its own.
    """
    return str(getattr(state, "ai_router_status", "") or "") == "ready"


def _router_status_line(state) -> str:
    """One honest line about the router: where it is, or why it isn't.

    Never a bare state name — "unavailable" means nothing to a user, while
    "No local model router is running" tells them what the Start button does.
    """
    status = str(getattr(state, "ai_router_status", "") or "")
    port = getattr(state, "ai_router_port", None)
    if status == "ready" and port:
        return f"Running on 127.0.0.1:{port} — replies are being served."
    if status == "stopped":
        return "The local model router stopped. Start it to use the assistant."
    if status == "unavailable":
        return "No local model router is running. Start it to use the assistant."
    if status == "starting":
        return "Looking for a local model router…"
    return "Router status unknown."


def build_ai_section(page: ft.Page, state, services) -> ft.Column:
    """The ASSISTANT settings block."""
    credits = getattr(services, "credits", None)

    async def _credits_copy_async() -> str:
        if credits is None:
            return "Assistant credits are unavailable in this build."
        try:
            is_premium = bool(getattr(state, "is_premium", False))
            balance = await credits.get_balance(is_premium=is_premium)
            if balance <= 0:
                # Same wording the assistant gate shows, so the two agree.
                return ai_credits.out_of_credits_notice(balance, is_premium)
            cap = credits.daily_cap(is_premium=is_premium)
            return f"{balance} of {cap} credits left today · resets at 00:00 UTC"
        except Exception:
            return "Credits update as you use the assistant."

    # The credits line is built fresh from observable state on every render.
    # An async loader must NOT write to a control that came out of this body:
    # those are frozen and the write raises "Frozen controls cannot be
    # updated." (`flet/controls/value_types.py:64-66`). Both DDGS and
    # lm-router put async data in observable state instead and let the body
    # repaint — `DDGS/src/components/settings/sections_premium.py:340-343`
    # states the rule in a comment; `lm-router/src/main.py:730-743` is the
    # same shape. `credits_copy` is a string, so `state.credits_copy`
    # notifies only when the wording actually changes.
    # `getattr` with a default so a caller can pass a state stub that
    # predates the field.
    saved_copy = getattr(state, "credits_copy", None)
    shown = saved_copy if saved_copy is not None else "Loading credits…"
    credits_text = ft.Text(
        shown,
        size=tokens.FONT_SM,
        color=ft.Colors.ON_SURFACE_VARIANT,
        selectable=True,
    )

    async def _load_credits():
        try:
            state.credits_copy = await _credits_copy_async()
        except Exception as ex:
            logger.warning("Credits publish failed: %s", ex)

    # Kick off the first read; later refreshes are driven by the wallet dialog.
    if saved_copy is None:
        page.run_task(_load_credits)

    # NOTE: this used to do `state.refresh_credits = _refresh_credits`. That
    # line froze the whole app, and the reason is worth keeping written down:
    #
    #   - `state` is `@ft.observable`, and `Observable.__setattr__` notifies
    #     whenever the new value is not equal to the old one.
    #   - `_refresh_credits` is a NEW closure on every call to this builder, so
    #     the comparison is never equal — it notified on EVERY render.
    #   - Every component that reads `AppStateCtx` subscribes to the whole
    #     state object, and a notification schedules that component for update.
    #   - So rendering Settings scheduled another render of Settings. Measured
    #     against flet's real session: 853 SettingsScreen rebuilds in 1.5 s,
    #     nothing painted, no exception logged.
    #
    # Nothing ever read it (the wallet dialog has its own refresh), so it was
    # dead code. Any future cross-component refresher belongs in a module-level
    # function or a non-observable attribute, NEVER a render-time assignment to
    # observable state.

    # There is no mode switch and no app-guide switch: both are always on.
    # They existed once and neither ever worked — `on_change` passed an
    # `async def` through a lambda, so flet (which only awaits a coroutine
    # *function*, base_control.py:514-555) created the coroutine and dropped
    # it, and the preference was never saved. The flag also defaulted to off,
    # so the assistant looked disabled to a user who could not enable it.

    # Subscribe to the router status. The row's text is built from
    # `ai_router_status`/`ai_router_port` on every render, so without this
    # read a status change published by the watchdog never reaches this
    # section — and the reload bump alone would not repaint it either.
    _ = getattr(state, "ai_router_status", "")
    _ = getattr(state, "router_status_revision", 0)

    # The live router row: what the app is actually talking to, and the one
    # action that makes it talk to something. The router starts with the app
    # (`services/router_watchdog`), so this button is the RECOVERY path — it
    # matters when the router died or was never found.
    #
    # A user request must be verified (`ensure_router(verify=True)`), because a
    # remembered dead port would otherwise make this button look inert.
    router_status_text = ft.Text(
        _router_status_line(state),
        size=tokens.FONT_SM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )

    async def _reload_router_status():
        """Re-read the router's own state and repaint the row.

        The row is frozen controls from the last render, so the loader cannot
        write into them — it writes observable state and lets the section
        rebuild, the way the credits line does.
        """
        state.router_status_revision = (getattr(state, "router_status_revision", 0) or 0) + 1

    # The address the app is actually talking to. Shown, not editable: neither
    # DDGS nor lm-router exposes a router URL in Settings (DDGS has no router
    # control at all; lm-router's is a numeric port for its own gateway), and
    # an editable box here was a footgun — it was pre-filled with the live URL,
    # so pressing Enter after the router auto-landed on 8083 saved that as a
    # permanent override and pinned the app to it, destroying the 8082..8092
    # re-probe. A stored override still works for anyone who has one; nothing
    # in the UI can set one now.
    router_url_text = ft.Text(
        _effective_router_url(state),
        size=tokens.FONT_SM,
        color=ft.Colors.ON_SURFACE_VARIANT,
        selectable=True,
        font_family="monospace",
    )


    # How hard the model thinks before answering. Both DDGS and lm-router expose
    # this dropdown with these exact options; "auto" sends no `reasoning_effort`
    # at all, so the gateway's own default applies.
    async def _save_thinking(value: str):
        depth = str(value or "auto").strip().lower()
        if depth not in constants.THINKING_DEPTHS:
            depth = "auto"
        state.ai_thinking = depth
        storage = getattr(services, "storage", None)
        if storage is not None:
            await storage.set(constants.STORAGE_AI_THINKING, depth)

    thinking_dropdown = ft.Dropdown(
        value=str(getattr(state, "ai_thinking", "auto") or "auto"),
        options=[
            ft.DropdownOption(
                key=depth,
                text={
                    "auto": "Auto (the router decides)",
                    "minimal": "Minimal",
                    "low": "Low",
                    "medium": "Medium",
                    "high": "High",
                }[depth],
            )
            for depth in constants.THINKING_DEPTHS
        ],
        width=220,
        text_size=tokens.FONT_SM,
        border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_MD),
        # `on_select`, not `on_change`: flet 1.0's Dropdown renamed it
        # (`controls/material/dropdown.py:226`).
        on_select=lambda e: page.run_task(_save_thinking, e.control.value),
    )


    def _pick_model(pg, st, svcs):
        from components.model_picker import show_model_picker

        show_model_picker(pg, st, svcs)

    # Generated from the catalog so the row cannot drift from what the router
    # actually offers right now.
    from components.model_picker import model_label as _picked_label

    model_label = ft.Text(
        _picked_label(state),
        size=tokens.FONT_SM,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.ON_SURFACE_VARIANT,
        selectable=True,
    )

    model_row = _row(
        "Assistant model",
        _model_subtitle(state),
        trailing=ft.Row(
            controls=[
                model_label,
                ft.OutlinedButton(
                    "Change",
                    on_click=lambda e: _pick_model(page, state, services),
                ),
            ],
            spacing=tokens.SPACE_SM,
            tight=True,
        ),
        icon=ft.Icons.MEMORY_ROUNDED,
    )


    return ft.Column(
        controls=[
            section_header("ASSISTANT"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Divider(height=tokens.SPACE_SM),
                        _row(
                            "Thinking",
                            "How hard the model thinks before it answers. "
                            "Deeper thinking takes longer and shows more in the "
                            "chat.",
                            trailing=thinking_dropdown,
                            icon=ft.Icons.PSYCHOLOGY_ROUNDED,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        _row(
                            "Router",
                            "The local model router that answers the assistant. "
                            "It starts automatically.",
                            icon=ft.Icons.ROUTER_ROUNDED,
                        ),
                        ft.Container(
                            content=ft.Column(
                                controls=[router_status_text, router_url_text],
                                spacing=tokens.SPACE_XXS,
                            ),
                            padding=ft.Padding(0, tokens.SPACE_XS, 0, 0),
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        model_row,
                        ft.Divider(height=tokens.SPACE_SM),
                        _row(
                            "Credits",
                            ai_credits.credits_are_for_copy(),
                            icon=ft.Icons.BOLT_ROUNDED,
                        ),
                        ft.Container(
                            content=credits_text,
                            padding=ft.Padding(0, tokens.SPACE_XS, 0, 0),
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


def _model_subtitle(state) -> str:
    """Subtitle for the model row — the picker's own, so the two agree."""
    from components.model_picker import model_subtitle

    return model_subtitle(state)



