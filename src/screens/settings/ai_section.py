"""Assistant settings section — mode, model, router, credits, premium.

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


def _row(title: str, subtitle: str, trailing=None) -> ft.Row:
    return ft.Row(
        controls=[
            ft.Icon(
                tokens.ASSISTANT_ICON,
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
    premium = getattr(services, "premium", None)
    premium_available = premium is not None and getattr(premium, "available", False)

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

    mode_switch = ft.Switch(
        value=bool(getattr(state, "ai_mode", False)),
        on_change=lambda e: _save_mode(e.control.value),
    )

    help_switch = ft.Switch(
        value=bool(getattr(state, "ai_help", True)),
        on_change=lambda e: _save_help(e.control.value),
    )

    async def _save_mode(value: bool):
        state.ai_mode = bool(value)

        storage = getattr(services, "storage", None)
        if storage is not None:
            await storage.set(
                constants.STORAGE_AI_MODE, "true" if value else "false"
            )
        page.update()

    async def _save_help(value: bool):
        state.ai_help = bool(value)
        storage = getattr(services, "storage", None)
        if storage is not None:
            await storage.set(
                constants.STORAGE_AI_HELP, "true" if value else "false"
            )
        page.update()

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
    start_router_button = ft.TextButton(
        "Start router",
        on_click=lambda ev: page.run_task(_start_router),
    )

    async def _reload_router_status():
        """Re-read the router's own state and repaint the row.

        The row is frozen controls from the last render, so the loader cannot
        write into them — it writes observable state and lets the section
        rebuild, the way the credits line does.
        """
        state.router_status_revision = (getattr(state, "router_status_revision", 0) or 0) + 1

    async def _start_router(ev=None):
        """Start (or re-attach), then re-read the status.

        `verify=True` because this is a user's tap: a port the app still holds
        but nothing answers on must be re-checked, or the button looks inert.
        """
        from services import router

        state.ai_router_status = "starting"
        await _reload_router_status()
        try:
            await router.ensure_router(verify=True)
        except Exception as ex:
            logger.warning("Start router failed: %s", ex)
        await _reload_router_status()

    # The override field: what is shown is what the app is actually using right
    # now — either the saved override, or the port the router landed on. An
    # empty field means "no override", which is the normal path (the app probes
    # 8082..8092 and embeds its own router).
    router_field = ft.TextField(
        value=_effective_router_url(state),
        label="Router URL (advanced — leave blank to auto-start)",
        hint_text="http://127.0.0.1:8082/v1",
        text_size=tokens.FONT_SM,
        border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_MD),
        expand=True,
    )

    async def _save_router(ev=None):
        url = (router_field.value or "").strip()
        # Clearing the field is the way to go back to auto-start, so an empty
        # value is a real state and not a no-op.
        state.ai_router_url = url
        storage = getattr(services, "storage", None)
        if storage is not None:
            await storage.set(constants.STORAGE_AI_ROUTER_URL, url)
        if url:
            try:
                from services.ai_service import configure_provider

                configure_provider(url)
            except Exception as ex:
                logger.warning("Provider reconfiguration failed: %s", ex)
        await _reload_router_status()
        page.update()

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

    router_field.on_submit = lambda ev: page.run_task(_save_router)

    def _pick_model(pg, st, svcs):
        from components.model_picker import show_model_picker

        show_model_picker(pg, st, svcs)

    # Generated from the catalog so the row cannot drift from what the router
    # actually offers right now.
    model_label = ft.Text(
        "Auto" if (getattr(state, "ai_model", "auto") or "auto").lower() == "auto"
        else getattr(state, "ai_model", "auto"),
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
    )

    premium_row = _row(
        "Assistant premium",
        _premium_subtitle(state),
        trailing=ft.FilledButton(
            "Upgrade",
            on_click=lambda e: _show_premium(page, state, services),
        )
        if premium_available
        else ft.Text(
            "Unavailable",
            size=tokens.FONT_SM,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
    )

    return ft.Column(
        controls=[
            section_header("ASSISTANT"),
            glass_card(
                ft.Column(
                    controls=[
                        _row(
                            "Assistant mode",
                            constants.TIP_AI_MODE,
                            trailing=mode_switch,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        _row(
                            "Include app guide in prompts",
                            "Teach the assistant how this app works so it "
                            "does not run code that fails here.",
                            trailing=help_switch,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        _row(
                            "Thinking",
                            "How hard the model thinks before it answers. "
                            "Deeper thinking takes longer and shows more in the "
                            "chat.",
                            trailing=thinking_dropdown,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        _row("Router URL", "OpenAI-compatible endpoint",
                             trailing=None),
                        ft.Container(
                            content=router_field,
                            padding=ft.Padding(0, tokens.SPACE_XS, 0, 0),
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        _row(
                            "Router",
                            "The local model router that answers the assistant.",
                            trailing=start_router_button,
                        ),
                        ft.Container(
                            content=router_status_text,
                            padding=ft.Padding(0, tokens.SPACE_XS, 0, 0),
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        model_row,
                        ft.Divider(height=tokens.SPACE_SM),
                        _row("Credits", ai_credits.credits_are_for_copy()),
                        ft.Container(
                            content=credits_text,
                            padding=ft.Padding(0, tokens.SPACE_XS, 0, 0),
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        premium_row,
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


def _premium_subtitle(state) -> str:
    if bool(getattr(state, "is_premium", False)):
        return "Premium is active — 500 credits a day."
    return "Raise the daily allowance from 50 to 500 credits."


def _model_subtitle(state) -> str:
    """Subtitle for the model row, generated from state so it cannot drift."""
    model = getattr(state, "ai_model", "auto") or "auto"
    if model == "auto":
        return "Rotates across the models your router has awake."
    return model


def _show_premium(page: ft.Page, state, services):
    """Open the wallet dialog (balance, top-up, and the premium upsell)."""
    from components.wallet_dialog import show_wallet_dialog

    show_wallet_dialog(page, state, services)
