"""Model pill — the assistant header's model selector.

An actual dropdown menu, not the dialog DDGS uses. The owner's call: LM
Router's `PopupMenuButton` + `PopupMenuItem` pattern reads better than a modal
list, because you can see the choices and the current pick at once without
leaving the transcript.

Taken from LM Router (`src/components/chat_controls.py` ModelPicker) and made
better on the points that mattered there:

* **Tier is visible per row.** LM Router colours the caption by rate tier;
  here the tier is also spelled out, because "high tier" and a colour are not
  the same thing when you cannot see colour.
* **`auto` explains itself.** Its row says what it does rather than just
  "Auto", and its caption names the tier it will actually serve.
* **The label never lies.** A model the router stopped offering falls back to
  the honest state ("Offline" / "Loading models…") instead of showing a stale
  name — the same rule as LM Router's discovering states.
* **Empty state carries an action.** Never a bare "No model": it says what is
  happening and offers the one thing that helps (Refresh, or Start router).
* **The four states are the router's four statuses**, mapped through
  `pill_state` the way DDGS maps them, so a dead router outranks a stale
  catalog and a saved model can never outlive the router itself.

Nothing here computes tier, order or latency: `services.model_catalog` reads
all of that from the router (see [[model-selection-is-read-not-computed]]).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import flet as ft

from core import tokens
from core.theme import brand_color

logger = logging.getLogger("model_pill")

_ICON_AUTO = ft.Icons.AUTO_AWESOME_ROUNDED
_ICON_MODEL = ft.Icons.MEMORY_ROUNDED
_ICON_OFFLINE = ft.Icons.CLOUD_OFF_ROUNDED

# A router the app last knew was alive, and which is not answering now.
_DEAD_STATUSES = ("stopped", "unavailable")

# Longest model name printed on the pill before it is elided. The full name
# still reaches the user through the pill's tooltip.
_LABEL_MAX_CHARS = 26


@dataclass(frozen=True)
class PillState:
    """Everything the pill renders, derived from the router's status.

    Kept as a value rather than read site-by-site so the label, the colour and
    the menu can never disagree, and so `ChatSession.refresh_model_chip` has a
    cheap signature to compare against (DDGS's `model_picker_state`).
    """

    label: str
    active: bool
    # True only while the app is genuinely still finding out. Once a fetch has
    # completed, an empty catalog is a real answer, not a wait.
    discovering: bool
    status: str
    selected: str
    # Empty-state copy for the menu, plus the action that helps.
    message: str = ""
    action: str = ""
    runner: object = None


def _tier_label(entry: dict) -> str:
    """The router's own tier, spelled out for the row caption."""
    from services import model_catalog

    tier = model_catalog.tier_of(entry)
    return {"high": "high tier", "medium": "medium tier"}.get(tier, "")


def _app_state():
    from core.state import state

    return state


async def start_router_and_refresh(page) -> bool:
    """Start (or re-attach to) the router, then make the pill say so.

    `verify=True` matters here: a remembered dead port must be re-checked
    rather than trusted, which is what made a "Start router" tap look inert.
    """
    from services import model_catalog, router

    try:
        port = await router.ensure_router(verify=True)
    except Exception:
        logger.warning("Start router failed", exc_info=True)
        return False
    if port is None:
        return False
    try:
        await model_catalog.refresh_catalog(model_catalog.router_url_for_read())
    except Exception:
        logger.debug("Catalog refresh after start failed", exc_info=True)
    _refresh_pill(page)
    return True


async def refresh_catalog_and_pill(page) -> bool:
    """Re-read the catalog against the live router, then repaint the pill."""
    from services import model_catalog

    try:
        await model_catalog.refresh_catalog(model_catalog.router_url_for_read())
    except Exception:
        logger.debug("Catalog refresh failed", exc_info=True)
        return False
    _refresh_pill(page)
    return True


def _refresh_pill(page) -> None:
    session = getattr(page, "_assistant_session", None) if page is not None else None
    refresh = getattr(session, "refresh_model_chip", None)
    if callable(refresh):
        try:
            refresh()
        except Exception:
            pass
    try:
        page.update()
    except Exception:
        pass


def pill_state() -> PillState:
    """What the pill should say, given the router's status and the catalog.

    The decision table is DDGS's (`DDGS/src/components/model_picker.py:45-115`),
    with one rule of ours kept from before the port: a live router with a
    catalog falls back to **Auto**, not to "Offline". DDGS shows Offline for a
    stale pick on a healthy router, which reads as a broken app when the
    assistant would in fact work.

    The rules, in the order they decide:

    1. **A dead router outranks everything.** The catalog is a snapshot; once
       the router is down it proves nothing, so "Offline" beats a model name.
    2. **`ready` means answers are being served**, even with an empty catalog:
       `turn_candidates` keeps `auto` as the final resort, so a turn would run.
       Saying "Offline" there would be a lie, and the empty menu offers Refresh
       so the user can re-read the catalog.
    3. **`starting` is the only label that implies a wait.**
    4. **The chosen name counts only while it is servable** — present in the
       catalog, or `auto`. A saved preference cannot outlive the router itself.
    5. **A live catalog with a stale pick falls back to Auto**, because the
       router's ranked best is real and the assistant would work.
    """
    from services import model_catalog
    from services.model_catalog import AUTO_MODEL_ID

    rows = model_catalog.pickable_models()
    status = str(getattr(_app_state(), "ai_router_status", "starting") or "starting")
    fetched = bool(model_catalog._catalog_fetched_at)
    selected = str(getattr(_app_state(), "ai_model", "") or "")

    current = next(
        (e for e in rows if str(e.get("id") or "").lower() == selected.lower()),
        None,
    )
    # `auto` is always servable while a router answers, even if the catalog
    # published no row for it — `turn_candidates` keeps it as the last resort.
    if current is None and selected.lower() == AUTO_MODEL_ID and status == "ready":
        current = {"id": AUTO_MODEL_ID}

    message = ""
    action = ""
    if status in _DEAD_STATUSES:
        label = "Offline"
        active = False
        message = (
            "The local model router stopped."
            if status == "stopped"
            else "No local model router is running. Replies wait for it."
        )
        action = "Start router"
    elif status == "starting":
        label = "Starting router…"
        active = False
        # Still finding out, but a start is the one thing that unblocks it —
        # a lone Refresh on a router that is not up yet does nothing.
        message = "Looking for available models…"
        action = "Start router"
    elif current is not None:
        label = "Auto" if selected.lower() == AUTO_MODEL_ID else selected
        active = True
        if not rows:
            # Up, but nothing to choose from: the turn still runs on the
            # gateway's rotation, and re-reading is the one thing that helps.
            message = "No models reported by the router."
            action = "Refresh"
    else:
        # Ready and the pick is not in the catalog: fall back to the ranked best.
        label = "Auto"
        active = True
        if not rows:
            message = "No models reported by the router."
            action = "Refresh"

    return PillState(
        label=label,
        active=active,
        discovering=status == "starting" and not fetched,
        status=status,
        selected=selected,
        message=message,
        action=action,
    )


def _elide(text: str) -> str:
    if len(text) <= _LABEL_MAX_CHARS:
        return text
    return text[: _LABEL_MAX_CHARS - 1] + "…"


def _menu_item(entry: dict, selected: bool, on_pick) -> ft.PopupMenuItem:
    """One model row: icon, name, and what the router says about it."""
    from services import model_catalog

    model_id = str(entry.get("id") or "")
    is_auto = model_id.lower() == "auto"
    hint = model_catalog.model_hint(entry)
    tier = _tier_label(entry)
    caption = " · ".join(part for part in (tier, hint) if part)

    name = "Auto" if is_auto else model_id
    if is_auto:
        caption = caption or "the router's ranked best model"

    lead = ft.Icon(
        _ICON_AUTO if is_auto else _ICON_MODEL,
        size=tokens.ICON_SM,
        color=brand_color() if selected else ft.Colors.ON_SURFACE_VARIANT,
    )
    return ft.PopupMenuItem(
        content=ft.Row(
            [
                lead,
                ft.Column(
                    [
                        ft.Text(
                            name,
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_400,
                            color=ft.Colors.ON_SURFACE,
                            no_wrap=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        *(
                            [
                                ft.Text(
                                    caption,
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    no_wrap=True,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                )
                            ]
                            if caption
                            else []
                        ),
                    ],
                    spacing=0,
                    expand=True,
                    tight=True,
                ),
                *(
                    [
                        ft.Icon(
                            ft.Icons.CHECK_ROUNDED,
                            size=tokens.ICON_SM,
                            color=brand_color(),
                        )
                    ]
                    if selected
                    else []
                ),
            ],
            spacing=tokens.SPACE_SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        on_click=lambda e, mid=model_id: on_pick(mid),
    )


def build_model_pill(page: ft.Page, *, on_pick=None) -> ft.PopupMenuButton:
    """The chat-header model dropdown.

    `on_pick(model_id)` is called with the chosen row's id. Where the pick is
    persisted is the caller's business, so this stays a pure control.

    The label, the colour and the menu all come from `pill_state`, so the three
    can never disagree about whether the router is up.
    """
    from services import model_catalog

    state = pill_state()
    rows = model_catalog.pickable_models()
    chosen = state.selected

    def _pick(model_id: str) -> None:
        if on_pick is not None:
            on_pick(model_id)

    items = [
        _menu_item(entry, str(entry.get("id") or "").lower() == chosen.lower(), _pick)
        for entry in rows
    ]

    if not items:
        # A menu that opens on nothing is a dead end. It says what is happening
        # and carries the one action that helps.
        async def _start(e=None):
            await start_router_and_refresh(page)

        async def _refresh(e=None):
            await refresh_catalog_and_pill(page)

        runner = _start if state.action == "Start router" else _refresh
        items.append(
            ft.PopupMenuItem(
                content=ft.Column(
                    [
                        ft.Text(
                            state.message or "No models reported by the router.",
                            size=tokens.FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            state.action or "Refresh",
                            size=tokens.FONT_XS,
                            weight=ft.FontWeight.W_600,
                            color=brand_color(),
                        ),
                    ],
                    spacing=0,
                    tight=True,
                ),
                on_click=lambda e: page.run_task(runner),
            )
        )

    label = state.label
    pill_color = (
        ft.Colors.ERROR
        if label == "Offline"
        else (brand_color() if state.active else ft.Colors.ON_SURFACE_VARIANT)
    )
    lead_icon = (
        _ICON_OFFLINE
        if label == "Offline"
        else (_ICON_AUTO if chosen.lower() == "auto" else _ICON_MODEL)
    )
    return ft.PopupMenuButton(
        content=ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        lead_icon,
                        size=tokens.ICON_SM,
                        color=pill_color,
                    ),
                    ft.Text(
                        _elide(label),
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.W_600,
                        color=pill_color,
                        no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Icon(
                        ft.Icons.EXPAND_MORE_ROUNDED,
                        size=12,
                        color=pill_color,
                    ),
                ],
                spacing=2,
                tight=True,
            ),
            # Same geometry as the credits chip so the two read as one family.
            padding=ft.Padding.symmetric(horizontal=7, vertical=3),
            border_radius=tokens.RADIUS_PILL,
            bgcolor=ft.Colors.with_opacity(0.1 if state.active else 0.06, pill_color),
        ),
        items=items,
        menu_position=ft.PopupMenuPosition.UNDER,
        tooltip=label,
    )
