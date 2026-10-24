"""Account and authentication settings section.

Restored from views/settings/auth_section.py:
- Auth status indicator (icon + email or "Not signed in")
- Signed-in method display (OAuth2 — the only supported sign-in; the old
  oauth2/adc dropdown was removed because flipping to ADC on a machine
  without Application Default Credentials bricked every backend call)
- Re-Authenticate button (clear_token → navigate to onboarding)
- Who Am I button (check_auth → AlertDialog with email/expiry/method)
- Compute Usage card (auto-loads on open, Refresh re-fetches, per-reason
  copy, shared 24h cache, fetched timestamp)

The usage card keeps its state at module level, NOT in the builder's local
scope: SettingsScreen is a component and re-renders on every observable it
touches (a theme toggle reads theme_revision through glass_card), so a
per-render dict would flash "Loading usage…" and refetch on each rebuild.
"""

from __future__ import annotations

import logging
import time

import flet as ft

from core import constants, tokens
from core.state import state
from core.styles import glass_card, section_header, tip_text
from core.theme import AppColors

logger = logging.getLogger("AccountSection")


def format_usage_values(usage: dict) -> tuple[list[tuple[str, str]], bool]:
    """Pure formatting for the USAGE card (importable for tests).

    Returns ((label, value) rows, needs_free_copy). Key names mirror upstream
    format_consumption_status; values use the same :.2f precision.
    """
    balance = float(usage.get("balance", 0.0) or 0.0)
    rate = float(usage.get("rate", 0.0) or 0.0)
    count = int(usage.get("assignments", 0) or 0)
    rows = [
        ("Compute-unit balance", f"{balance:.2f} compute units"),
        ("Usage rate", f"{rate:.2f}/hr"),
        ("Active assignments", f"{count}"),
    ]
    return rows, balance <= 0


def free_tier_copy() -> str:
    return (
        "No paid compute-unit balance — free-tier runtimes only. "
        "Usage rate still applies to paid hardware."
    )


# ── Usage card state (module-level: survives parent rebuilds) ───────────────
# States: idle → loading → value | stale-with-values | per-reason error.
# Auto-load fires once per signed-in identity, never per re-render.
_USAGE = {
    "usage": None,
    "error": False,
    "loading": False,
    "loaded": False,
    "reason": "no-cache",
    "updated_at": "",
}
# Live handles of the most recent render: the service bundle the loader reads
# back at await time plus the controls it re-renders into. A fetch started
# before a rebuild must write into the NEW controls, so the loader never
# captures the ones it was created with.
_USAGE_VIEW: dict = {
    "page": None,
    "services": None,
    "auth_method": None,
    "body": None,
    "refresh": None,
}
# Identity the auto-load last ran for (sentinel: never). Keyed on auth so
# sign-out/sign-in refetches while a theme toggle does not.
_USAGE_AUTOLOAD_KEY: object = object()

# How old the numbers may be before re-entering Settings re-checks them.
# The card's own cache lasts 24h, so without this a user who leaves Settings
# open all morning is still looking at the numbers from when they arrived.
USAGE_STALE_SEC = 300.0


def _format_updated(store: dict) -> str:
    """How old the numbers are, in words: "As of 3 minutes ago".

    A clock time ("Updated 14:32") answers "when was this fetched" only if the
    reader does the subtraction. The age answers the question the reader
    actually has: "can I trust these?"
    """
    ts = store.get("updated_at") or ""
    if not ts:
        return ""
    try:
        age = time.time() - float(ts)
    except (TypeError, ValueError, OSError, OverflowError):
        return ""
    if age < 0:
        age = 0.0
    if age < 60:
        return "As of just now"
    minutes = int(age // 60)
    if minutes < 60:
        return f"As of {minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = int(minutes // 60)
    if hours < 24:
        return f"As of {hours} hour{'s' if hours != 1 else ''} ago"
    days = int(hours // 24)
    return f"As of {days} day{'s' if days != 1 else ''} ago"


def _usage_is_stale(store: dict) -> bool:
    """Whether the shown numbers are old enough to be worth re-checking.

    Only meaningful when a fetch actually succeeded: without a timestamp there
    is no age to judge, and the last attempt already said what it could.
    """
    ts = store.get("updated_at") or ""
    if not ts:
        return False
    try:
        return (time.time() - float(ts)) > USAGE_STALE_SEC
    except (TypeError, ValueError, OSError, OverflowError):
        return False


def _usage_row(label: str, value: str) -> ft.Row:
    return ft.Row(
        controls=[
            ft.Text(
                label,
                size=tokens.FONT_SM,
                color=ft.Colors.ON_SURFACE_VARIANT,
                expand=True,
            ),
            ft.Text(value, size=tokens.FONT_SM, weight=ft.FontWeight.W_600),
        ],
        spacing=tokens.SPACE_SM,
    )


def _usage_spinner_row(store: dict) -> list:
    """Loading indicator, with the previous values dimmed underneath.

    Shown on the first auto-load AND on every Refresh, so a re-fetch that
    returns identical numbers still proves it ran.
    """
    rows = [
        ft.Row(
            controls=[
                ft.ProgressRing(width=tokens.SPINNER_SM, height=tokens.SPINNER_SM),
                ft.Text(
                    "Loading usage…",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=tokens.SPACE_SM,
        )
    ]
    usage = store["usage"]
    if usage is not None:
        rows.extend(
            _usage_row(label, value) for label, value in format_usage_values(usage)[0]
        )
    return rows


def _usage_rows(store: dict) -> list:
    usage = store["usage"]
    if not store["loaded"] or store["loading"]:
        return _usage_spinner_row(store)
    if usage is None:
        reason = store.get("reason") or "no-cache"
        copy = {
            "signed-out": "Sign in to load your compute-unit balance.",
            "offline": "You're offline — reconnect to load usage.",
            "fetch-failed": "Couldn't reach Colab — check your connection and retry.",
            "no-cache": "Usage unavailable. Tap Check now to retry.",
        }.get(reason, "Usage unavailable. Tap Check now to retry.")
        return [
            ft.Text(
                copy,
                size=tokens.FONT_SM,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            )
        ]
    rows = [_usage_row(label, value) for label, value in format_usage_values(usage)[0]]
    _, needs_free_copy = format_usage_values(usage)
    if needs_free_copy:
        rows.append(tip_text(free_tier_copy()))
    if store["error"]:
        rows.append(tip_text("Couldn't refresh usage — showing last known values."))
    elif usage.get("cached"):
        rows.append(tip_text("Cached values — tap Check now for the latest."))
    stamped = _format_updated(store)
    if stamped:
        rows.append(tip_text(stamped))
    return rows


def _usage_header() -> ft.Row:
    refresh_btn = ft.TextButton(
        "Check now",
        icon=ft.Icons.REFRESH_ROUNDED,
        style=ft.ButtonStyle(
            text_style=ft.TextStyle(size=tokens.FONT_SM),
            icon_size=tokens.ICON_SM,
        ),
        disabled=_USAGE["loading"],
        on_click=lambda e: page_run_task(_on_usage_refresh),
    )
    _USAGE_VIEW["refresh"] = refresh_btn
    return ft.Row(
        controls=[
            ft.Icon(
                ft.Icons.DATA_USAGE_ROUNDED,
                size=tokens.ICON_LG,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Text(
                "Compute Usage",
                size=tokens.FONT_MD,
                weight=ft.FontWeight.W_500,
                expand=True,
            ),
            refresh_btn,
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=tokens.SPACE_MD,
    )


def page_run_task(coro_fn, *args) -> None:
    """Schedule a coroutine function on the live page (no-op without one)."""
    page = _USAGE_VIEW.get("page")
    if page is None:
        return
    try:
        page.run_task(coro_fn, *args)
    except Exception as ex:  # detached page during teardown
        logger.warning("Usage task scheduling failed (%s): %s", type(ex).__name__, ex)


def _refresh_usage_view() -> None:
    """Repaint the card by rebuilding it from the store.

    This used to write to the controls the previous render had produced —
    `body.controls = ...`, `refresh_btn.disabled = ...`, then `page.update()`.
    Those controls came out of `build_account_section`'s component body, so
    flet had frozen them, and every one of those writes raised
    "Frozen controls cannot be updated."
    (`flet/controls/value_types.py:64-66`).

    Both references publish the data instead of poking the widget:
    `lm-router/src/main.py:730-743` writes `state.gateway_counts` and lets the
    render body rebuild from it, and DDGS states the rule in a comment at
    `src/components/settings/sections_premium.py:340-343` — *"Never assign to a
    control: this card is a rendered component, so its controls are frozen.
    Write the observable instead and let the component repaint."*

    `usage_revision` is a plain int, so it notifies only when it changes, and
    a subscribed screen rebuilds the card from `_USAGE` on the next render.
    """
    try:
        state.usage_revision = (getattr(state, "usage_revision", 0) or 0) + 1
    except Exception as ex:
        logger.warning("Usage view update failed (%s): %s", type(ex).__name__, ex)


def _empty_reason() -> str:
    """Why a fetch came back with no values.

    The cache layer folds "no cache + fetch refused" into a bare None, which
    would erase the distinction between signed-out, offline and unreachable.
    This mirrors the branch order in usage_ops.get_usage_impl so the copy
    shown can never disagree with the backend's own decision.
    """
    from core.state import state as app_state

    if not getattr(app_state, "is_authenticated", False):
        return "signed-out"
    if not getattr(app_state, "is_online", True):
        return "offline"
    return "fetch-failed"


async def _load_usage(force: bool = False):
    from services.usage_cache import get_usage_cached

    _USAGE["loading"] = True
    _USAGE["loaded"] = True
    _refresh_usage_view()
    try:
        services = _USAGE_VIEW.get("services")
        if services is None:
            logger.warning("Usage load skipped: card was never bound to services")
            _USAGE["usage"] = None
            _USAGE["reason"] = "fetch-failed"
            return
        if force:
            try:
                await services.storage.delete(constants.STORAGE_USAGE_UPDATED_AT)
            except Exception as ex:
                logger.warning(
                    "Usage force-refresh delete failed (%s): %s",
                    type(ex).__name__,
                    ex,
                )
        result = await get_usage_cached(
            services, _USAGE_VIEW.get("auth_method") or "oauth2"
        )
        reason = (
            (result or {}).get("reason", "no-cache")
            if result is not None
            else _empty_reason()
        )
        _USAGE["usage"] = result
        _USAGE["reason"] = reason
        # A fetch that failed while values were shown must say so — otherwise
        # the "Cached values" footnote reads as fresh.
        _USAGE["error"] = reason == "fetch-failed"
        if result is not None:
            try:
                ts = await services.storage.get(constants.STORAGE_USAGE_UPDATED_AT)
                _USAGE["updated_at"] = ts or ""
            except Exception:
                pass
    except Exception as ex:
        logger.warning("Usage load failed (%s): %s", type(ex).__name__, ex)
        _USAGE["error"] = True
        _USAGE["reason"] = "fetch-failed"
    finally:
        _USAGE["loading"] = False
    _refresh_usage_view()


async def _on_usage_refresh(e=None):
    await _load_usage(force=True)


def _usage_autoload_identity(state) -> str:
    """Identity the auto-load is keyed on: who is signed in (or nobody)."""
    if not getattr(state, "is_authenticated", False):
        return ""
    return getattr(state, "auth_email", "") or "signed-in"


def reset_usage_card() -> None:
    """Forget card state + autoload marker (used on re-auth/sign-out paths)."""
    global _USAGE_AUTOLOAD_KEY
    _USAGE.update(
        {"usage": None, "error": False, "loading": False, "loaded": False,
         "reason": "no-cache", "updated_at": ""}
    )
    _USAGE_AUTOLOAD_KEY = object()


def build_account_section(page: ft.Page, state, services) -> ft.Column:
    global _USAGE_AUTOLOAD_KEY

    # ── Auth status indicator ───────────────────────────
    auth_status_icon = (
        ft.Icons.CHECK_CIRCLE_ROUNDED
        if state.is_authenticated
        else ft.Icons.ERROR_ROUNDED
    )
    auth_status_color = AppColors.SUCCESS if state.is_authenticated else AppColors.ERROR
    auth_status_text = (
        f"Signed in as {state.auth_email}"
        if state.is_authenticated
        else "Not signed in"
    )

    # ── Handlers ──────────────────────────────────────────────────────────────
    async def _on_reauth(e):
        def _close_confirm(ev=None):
            page.pop_dialog()

        async def _confirm_reauth(ev=None):
            page.pop_dialog()
            try:
                await services.colab.clear_token()
            except Exception as ex:
                logger.warning("Failed to clear token during reauth: %s", ex)
            state.is_authenticated = False
            state.auth_email = ""
            state.onboarding_done = False
            reset_usage_card()
            await services.storage.set(constants.STORAGE_ONBOARDING_DONE, "false")
            page.update()

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Re-Authenticate?", weight=ft.FontWeight.BOLD),
                content=ft.Text(
                    "This will clear your stored Google Colab credentials and return you to the onboarding screen. Do you want to continue?"
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=_close_confirm),
                    ft.FilledButton(
                        "Continue",
                        on_click=lambda ev: page.run_task(_confirm_reauth),
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    async def _on_whoami(e):
        try:
            result = await services.colab.check_auth()
        except Exception as ex:
            result = {"authenticated": False, "error": str(ex)}

        if result.get("authenticated"):
            msg = (
                f"Email: {result.get('email', 'unknown')}\n"
                f"Expires: {result.get('expires_in', 'unknown')}\n"
                f"Method: {result.get('auth_method', state.auth_method)}"
            )
        else:
            msg = "Not authenticated"

        def _close_info(e=None):
            page.pop_dialog()

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Who Am I"),
                content=ft.Text(msg, selectable=True),
                actions=[ft.TextButton("OK", on_click=_close_info)],
            )
        )

    # ── Signed-in method display (OAuth2 only — no selector) ─────────────────
    current_tip = constants.TIP_AUTH_OAUTH2

    # ── Compute-unit usage card ──────────────────────────────────────────────
    # Auto-loads on open; Refresh re-fetches. Reads through the shared 24h
    # cache (usage_cache via services.storage); never raises into Flet.
    #
    # The loader must not close over `services`/`page` — a fetch can outlive the
    # render that started it (and write into controls that render already
    # replaced) — so every live reference is published through _USAGE_VIEW and
    # the loader reads it back at await time.
    _USAGE_VIEW["page"] = page
    _USAGE_VIEW["services"] = services
    _USAGE_VIEW["auth_method"] = state.auth_method

    # Subscribe to the revision that publishes a fetched value. Without this
    # read this section never re-renders when one lands, which was the whole
    # reason the old code reached into the live controls (and hit the freeze).
    # `getattr` with a default so a caller can pass a state stub that predates
    # the field, the way `_effective_router_url` and `_router_is_up` already do.
    _ = getattr(state, "usage_revision", 0)

    usage_body = ft.Column(controls=_usage_rows(_USAGE), spacing=tokens.SPACE_XS)
    _USAGE_VIEW["body"] = usage_body

    usage_card = glass_card(
        ft.Column(
            controls=[
                _usage_header(),
                ft.Divider(height=tokens.SPACE_SM),
                usage_body,
            ],
            spacing=tokens.SPACE_SM,
        ),
        margin=ft.Margin(
            tokens.SPACE_LG,
            tokens.SPACE_XS,
            tokens.SPACE_LG,
            tokens.SPACE_XS,
        ),
    )

    # Auto-load once per signed-in identity. A rebuild with the same identity
    # keeps the stored values (no refetch, no loading flash).
    identity = _usage_autoload_identity(state)
    new_identity = _USAGE_AUTOLOAD_KEY != identity
    stale = (not new_identity) and _usage_is_stale(_USAGE)
    if new_identity or stale:
        _USAGE_AUTOLOAD_KEY = identity
        if stale:
            page_run_task(_load_usage, True)
        else:
            page_run_task(_load_usage)

    return ft.Column(
        controls=[
            section_header("AUTHENTICATION"),
            glass_card(
                ft.Column(
                    controls=[
                        # Auth status row
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    auth_status_icon,
                                    size=tokens.ICON_LG,
                                    color=auth_status_color,
                                ),
                                ft.Text(
                                    auth_status_text,
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                    expand=True,
                                ),
                            ],
                            spacing=tokens.SPACE_SM,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        # Signed-in method (display only — OAuth2)
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.VPN_KEY_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Auth Method",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(current_tip),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Text(
                                    "OAuth2",
                                    size=tokens.FONT_SM,
                                    weight=ft.FontWeight.W_600,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        # Re-Authenticate + Who Am I buttons
                        ft.Row(
                            controls=[
                                ft.OutlinedButton(
                                    constants.LBL_RE_AUTH,
                                    icon=ft.Icons.REFRESH_ROUNDED,
                                    on_click=lambda e: page.run_task(_on_reauth, e),
                                    expand=True,
                                ),
                                ft.OutlinedButton(
                                    "Who Am I",
                                    icon=ft.Icons.PERSON_SEARCH_ROUNDED,
                                    on_click=lambda e: page.run_task(_on_whoami, e),
                                    expand=True,
                                ),
                            ],
                            spacing=tokens.SPACE_SM,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG,
                    tokens.SPACE_XS,
                    tokens.SPACE_LG,
                    tokens.SPACE_XS,
                ),
            ),
            section_header("USAGE"),
            usage_card,
        ],
        spacing=0,
    )
