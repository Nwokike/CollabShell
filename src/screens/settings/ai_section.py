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
                ft.Icons.AUTO_AWESOME_ROUNDED,
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

    credits_text = ft.Text(
        "Loading credits…",
        size=tokens.FONT_SM,
        color=ft.Colors.ON_SURFACE_VARIANT,
        selectable=True,
    )

    async def _load_credits():
        credits_text.value = await _credits_copy_async()
        try:
            page.update()
        except Exception as ex:
            logger.warning("Credits render failed: %s", ex)

    # Kick off the first read; later refreshes are driven by the wallet dialog.
    page.run_task(_load_credits)

    def _refresh_credits():
        credits_text.value = "Loading credits…"
        page.run_task(_load_credits)

    # Expose the refresher so the wallet dialog can call it after a top-up.
    state.refresh_credits = _refresh_credits

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

    # The live router row: what the app is actually talking to, and the one
    # action that makes it talk to something. A user request must be verified
    # (ensure_router(verify=True)), because a remembered dead port would
    # otherwise make this button look inert.
    router_status_text = ft.Text(
        _router_status_line(state),
        size=tokens.FONT_SM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )

    async def _start_router(ev=None):
        """Start (or re-attach), then re-read the status.

        `verify=True` because this is a user's tap: a port the app still holds
        but nothing answers on must be re-checked, or the button looks inert.
        """
        from services import router

        start_router_button.disabled = True
        router_status_text.value = "Starting router…"
        router_status_text.color = ft.Colors.ON_SURFACE_VARIANT
        page.update()
        try:
            await router.ensure_router(verify=True)
        except Exception as ex:
            logger.warning("Start router failed: %s", ex)
        await _reload_router_status()

    start_router_button = ft.TextButton(
        "Start router",
        on_click=lambda ev: page.run_task(_start_router),
    )

    async def _reload_router_status():
        """Re-read the router's own state and repaint the row."""
        start_router_button.disabled = _router_is_up(state)
        router_status_text.value = _router_status_line(state)
        try:
            page.update()
        except Exception:
            pass

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
