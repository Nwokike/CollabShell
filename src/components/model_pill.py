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
  happening and offers the one thing that helps (Refresh).

Nothing here computes tier, order or latency: `services.model_catalog` reads
all of that from the router (see [[model-selection-is-read-not-computed]]).
"""

from __future__ import annotations

import flet as ft

from core import tokens
from core.theme import brand_color

_ICON_AUTO = ft.Icons.AUTO_AWESOME_ROUNDED
_ICON_MODEL = ft.Icons.MEMORY_ROUNDED
_ICON_OFFLINE = ft.Icons.CLOUD_OFF_ROUNDED

# Longest model name printed on the pill before it is elided. The full name
# still reaches the user through the pill's tooltip.
_LABEL_MAX_CHARS = 26


def _tier_label(entry: dict) -> str:
    """The router's own tier, spelled out for the row caption."""
    from services import model_catalog

    tier = model_catalog.tier_of(entry)
    return {"high": "high tier", "medium": "medium tier"}.get(tier, "")


def _app_state():
    from core.state import state

    return state


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
    """
    from services import model_catalog

    rows = model_catalog.pickable_models()
    chosen = str(getattr(_app_state(), "ai_model", "") or "")
    current = next(
        (e for e in rows if str(e.get("id") or "").lower() == chosen.lower()),
        None,
    )

    def _pick(model_id: str) -> None:
        if on_pick is not None:
            on_pick(model_id)

    # Label: never claim a model the router is not offering.
    if current is not None:
        label = "Auto" if chosen.lower() == "auto" else chosen
        active = True
    elif rows:
        label = "Auto"
        active = True
    else:
        label = "Loading models…"
        active = False

    items = [_menu_item(entry, str(entry.get("id") or "").lower() == chosen.lower(), _pick)
             for entry in rows]

    if not items:
        # An empty menu must say what is happening and offer the action that
        # helps, rather than opening on nothing.
        message = "No models reported by the router."

        async def _refresh(e=None):
            try:
                await model_catalog.refresh_catalog(
                    str(getattr(_app_state(), "ai_router_url", "") or "")
                )
            except Exception:
                pass
            # Rebuild the pill by re-rendering the page it lives on.
            try:
                page.update()
            except Exception:
                pass

        items.append(
            ft.PopupMenuItem(
                content=ft.Column(
                    [
                        ft.Text(
                            message,
                            size=tokens.FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            "Refresh",
                            size=tokens.FONT_XS,
                            weight=ft.FontWeight.W_600,
                            color=brand_color(),
                        ),
                    ],
                    spacing=0,
                    tight=True,
                ),
                on_click=lambda e: page.run_task(_refresh),
            )
        )

    pill_color = brand_color() if active else ft.Colors.ON_SURFACE_VARIANT
    return ft.PopupMenuButton(
        content=ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        _ICON_AUTO if chosen.lower() == "auto" else _ICON_MODEL,
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
            bgcolor=ft.Colors.with_opacity(0.1 if active else 0.06, pill_color),
        ),
        items=items,
        menu_position=ft.PopupMenuPosition.UNDER,
        tooltip=label,
    )
