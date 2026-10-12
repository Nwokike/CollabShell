"""Model picker — the assistant's model, chosen from the router's own catalog.

Nothing here is hardcoded. Tier, status, latency and the rate label are fields
the gateway publishes; this dialog only displays them and records the choice.
A router whose catalog changes changes this list without a code change.

The one entry that is not ranked is ``auto``, which the gateway publishes as a
real row. When the gateway does not publish it, the picker says so rather than
pretending, and the stored preference resolves to the ranked head.
"""

from __future__ import annotations

import logging

import flet as ft

from core import constants, tokens
from core.styles import tip_text

logger = logging.getLogger("ModelPicker")

AUTO = "auto"


def _http_client(timeout: float = 30.0):
    """The httpx client used for router calls.

    A named seam so tests can substitute a mock transport without patching
    ``httpx.AsyncClient`` globally (the openai SDK subclasses it, and a global
    patch breaks the SDK at import time).
    """
    import httpx

    return httpx.AsyncClient(timeout=timeout)


def _tier_chip(tier: str) -> ft.Container:
    """The gateway's tier as a small chip. Colour only — never a policy claim."""
    palette = {
        "high": ft.Colors.PRIMARY,
        "medium": ft.Colors.ON_SURFACE_VARIANT,
        "low": ft.Colors.OUTLINE,
        "minimal": ft.Colors.OUTLINE,
    }
    label = {"high": "High", "medium": "Medium", "low": "Low", "minimal": "Minimal"}
    colour = palette.get(tier, ft.Colors.OUTLINE)
    return ft.Container(
        content=ft.Text(
            label.get(tier, tier.title()),
            size=tokens.FONT_XS,
            weight=ft.FontWeight.W_600,
            color=colour,
        ),
        padding=ft.Padding(tokens.SPACE_SM, tokens.SPACE_XXS),
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.with_opacity(0.12, colour),
    )


def _model_row(entry: dict, selected: bool, on_pick) -> ft.ListTile:
    from services import model_catalog

    model_id = entry["id"]
    subtitle = model_catalog.model_hint(entry)
    trailing: list = []
    tier = model_catalog.tier_of(entry)
    if model_id.lower() != AUTO:
        trailing.append(_tier_chip(tier))
    latency = entry.get("latency_ms")
    if isinstance(latency, (int, float)) and not isinstance(latency, bool):
        trailing.append(
            ft.Text(
                f"{latency}ms" if latency < 1000 else f"{latency / 1000:.1f}s",
                size=tokens.FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )

    return ft.ListTile(
        leading=ft.Icon(
            ft.Icons.CHECK_ROUNDED if selected else ft.Icons.CIRCLE_OUTLINED,
            color=ft.Colors.PRIMARY if selected else ft.Colors.ON_SURFACE_VARIANT,
        ),
        title=ft.Text(model_id),
        subtitle=tip_text(subtitle) if subtitle else None,
        trailing=ft.Row(controls=trailing, spacing=tokens.SPACE_XS, tight=True)
        if trailing
        else None,
        on_click=lambda e, mid=model_id: on_pick(mid),
    )


def show_model_picker(page: ft.Page, state, services) -> None:
    """Dialog listing the router's ranked models, with ``auto`` first."""

    async def _load():
        from services import model_catalog, router

        # The router's actual port first, then the override, then the constant.
        # Refreshing the catalog from a stale 8082 when the router answered on
        # 8083 is how the picker shows models nobody can use.
        router_url = (
            router.current_url()
            or str(getattr(state, "ai_router_url", "") or "").strip()
            or constants.AI_DEFAULT_ROUTER_URL
        )
        try:
            from services.ai_service import configure_provider

            configure_provider(router_url)
        except Exception as ex:
            logger.warning("Provider configuration failed: %s", ex)
        entries = await model_catalog.refresh_catalog(router_url)
        _render(entries)

    selected = {"id": getattr(state, "ai_model", AUTO) or AUTO}
    body = ft.Column(controls=[], spacing=tokens.SPACE_XS, tight=True)
    dialog = ft.AlertDialog(
        title=ft.Text("Assistant model"),
        content=ft.Container(content=body, width=380),
        actions=[
            ft.TextButton("Close", on_click=lambda ev: page.pop_dialog()),
        ],
    )

    async def _pick(model_id: str):
        selected["id"] = model_id
        state.ai_model = model_id
        storage = getattr(services, "storage", None)
        if storage is not None:
            await storage.set(constants.STORAGE_AI_MODEL, model_id)
        page.pop_dialog()
        page.update()

    def _render(entries: list[dict]):
        body.controls.clear()
        if not entries:
            body.controls.extend(
                [
                    tip_text(
                        "No high or medium tier models are active on the "
                        "router. Start it and try again — its catalog decides "
                        "what is offered here."
                    ),
                ]
            )
        else:
            for entry in entries:
                body.controls.append(
                    _model_row(
                        entry, entry["id"] == selected["id"], lambda mid: page.run_task(_pick, mid)
                    )
                )
        try:
            page.update()
        except Exception as ex:
            logger.warning("Model picker render failed: %s", ex)

    page.show_dialog(dialog)
    page.run_task(_load)


def model_label(state) -> str:
    """The one-line label for the settings row and the header pill.

    Generated from the catalog, never hand-typed, so it cannot drift from what
    the router actually offers.
    """
    from services import model_catalog

    chosen = str(getattr(state, "ai_model", AUTO) or AUTO)
    if chosen.lower() == AUTO:
        return "Auto" if model_catalog.has_auto() else "Auto (router default)"
    return chosen


def model_subtitle(state) -> str:
    """Subtitle for the settings model row."""
    from services import model_catalog

    chosen = str(getattr(state, "ai_model", AUTO) or AUTO)
    catalog = model_catalog.catalog()
    entry = next(
        (e for e in catalog if e["id"].lower() == chosen.lower()), None
    )
    if entry is not None:
        return model_catalog.model_hint(entry)
    if chosen.lower() == AUTO:
        if model_catalog.has_auto():
            return "Rotates across available models"
        return "Uses the router's ranked best model"
    return "Not offered by the router right now"
