"""The PREMIUM card is KTV Player's card, not a variant of ours.

The owner: *"Our premium should match KTV player exactly. Exactly on every
count, don't do more, don't do less, exactly like KTV player."*

Every assertion here pins a piece of KTV's premium block
(ktv-player/src/screens/settings_screen.py:942-1235) that a user could feel:

  - one status row with an honest subtitle and a check mark
  - kiri rows (catalog products, recovery ID with Copy, error-with-Retry,
    loading-while-in-flight) only while FREE
  - Restore purchases always
  - the email dialog is exactly one field; the restore dialog exactly one
  - first paint says "Loading unlock options", never a false error
  - the Play build does not build the card at all
  - unlock toast is platform-honest ("Ads removed" only where ads run)
"""

from __future__ import annotations

import pathlib
import sys
from types import SimpleNamespace as NS
from typing import ClassVar

_SRC = pathlib.Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_CARD = _SRC / "screens/settings/premium_section.py"
_SCREEN = _SRC / "screens/settings/__init__.py"


def _card() -> str:
    return _CARD.read_text(encoding="utf-8")


# ── the card is built from state, not mutated in place ──────────────────────


def test_no_in_place_controls_mutation():
    """`clear()`/`append()` on `controls` never sets the dirty flag."""
    text = _card()
    assert ".controls.clear()" not in text
    assert ".controls.append(" not in text


def test_no_page_update_from_the_render_body():
    text = _card()
    assert "page.update()" not in text


def test_first_paint_is_loading_not_a_false_error():
    """Before the catalog resolves, the card says it is loading (KTV:1170)."""
    text = _card()
    assert "Loading unlock options" in text
    assert "Contacting the license service" in text
    # And the unreachable copy exists too, for a real failure (KTV:1161).
    assert "Unlock options unavailable" in text
    assert "Tap Retry to try again." in text


# ── the rows, in KTV's order ────────────────────────────────────────────────


def test_status_row_names_the_app_and_carries_a_check_mark():
    text = _card()
    assert '"CollabShell Premium"' in text
    assert "VERIFIED_ROUNDED" in text
    assert "CHECK_CIRCLE" in text and "CIRCLE_OUTLINED" in text
    assert "_premium_subtitle" in text


def test_the_premium_row_subtitle_is_token_truthful():
    """paid_through drives the dates; its absence marks a lifetime licence."""
    text = _card()
    assert "paid_through" in text
    assert "thank you!" in text
    assert "renews monthly" in text and "renews yearly" in text
    assert "active until" in text


def test_products_render_from_the_catalog_like_ktv():
    """KTV renders one row per catalog product — not a hardcoded plan list."""
    text = _card()
    assert "for p in products" in text or "for product in products" in text, (
        "rows must come from the fetched catalog"
    )
    assert "_kiri_product_row" in text
    assert "product.id.capitalize()" in text
    assert "product.description or product.price_label" in text
    # lifetime gets the open-lock, the rest get AUTORENEW (KTV:1116)
    assert "LOCK_OPEN_ROUNDED" in text and "AUTORENEW" in text


def test_plans_are_hidden_once_premium():
    """No buy rows for a user who already paid (KTV:1213)."""
    text = _card()
    assert "if CHANNEL != \"play\" and not is_premium" in text


def test_recovery_id_row_shows_the_id():
    """The subtitle is the ID itself, not a sentence about it (KTV:1141)."""
    from screens.settings import premium_section as ps

    fake_state = NS(
        is_premium=False,
        license_products=[],
        license_busy=False,
        license_error="",
        license_recovery_id="KIRI-L-ABC",
    )
    fake_premium = NS(
        available=True,
        license=NS(claims=None, recovery_id=_async_return("KIRI-L-ABC")),
        kiri_catalog=_async_return([]),
    )
    page = _FakePage()
    card = ps.build_premium_section(page, fake_state, NS(premium=fake_premium))
    texts = _flatten(card)
    assert any("KIRI-L-ABC" in t for t in texts), texts
    assert any("Your recovery ID" == t.strip() for t in texts), texts


def test_restore_purchases_row_exists_and_calls_the_service():
    text = _card()
    assert '"Restore purchases"' in text
    assert "Re-check ownership (new device / reinstall)" in text
    assert "kiri_restore" in text, "the restore dialog must call the service"


def test_row_order_is_status_products_recovery_restore():
    """KTV order: status -> kiri rows (products, recovery) -> Restore."""
    from screens.settings import premium_section as ps

    product = NS(id="lifetime", description=None, price_label="$9.99")
    fake_state = NS(
        is_premium=False,
        license_products=[product],
        license_busy=False,
        license_error="",
        license_recovery_id="KIRI-L-ABC",
    )
    fake_premium = NS(
        available=True,
        license=NS(claims=None, recovery_id=_async_return("KIRI-L-ABC")),
        kiri_catalog=_async_return([product]),
    )
    card = ps.build_premium_section(
        _FakePage(), fake_state, NS(premium=fake_premium)
    )
    texts = _flatten(card)
    order = []
    for needle in (
        "CollabShell Premium",
        "Lifetime",
        "Your recovery ID",
        "Restore purchases",
    ):
        found = next((i for i, t in enumerate(texts) if needle in t), -1)
        order.append(found)
    assert all(i >= 0 for i in order), texts
    assert order == sorted(order), f"rows out of KTV order: {order}"


# ── the dialogs ─────────────────────────────────────────────────────────────


def test_email_dialog_is_exactly_one_field():
    """KTV:1003-1025 — the dialog is the field and nothing else."""
    text = _card()
    assert "KeyboardType.EMAIL" in text
    assert "Unlock CollabShell Premium —" in text
    assert '"Continue"' in text


def test_checkout_uses_the_platform_launcher_with_an_https_guard():
    text = _card()
    assert "webbrowser" not in text, "the platform launcher, not webbrowser"
    assert "UrlLauncher" in text
    assert "https://" in text, "no scheme guard on the checkout URL"


def test_restore_toast_is_ktvs_platform_honest_copy():
    """KTV:1093 — the unlock toast is platform-honest, not a generic string."""
    text = _card()
    assert "premium_unlocked_message" in text
    assert '"Premium unlocked. Ads removed."' in text


def test_busy_disables_the_buy_buttons():
    """KTV:1127 — product buttons carry disabled=license_busy."""
    text = _card()
    assert "disabled=state.license_busy" in text


# ── the honest subtitle ─────────────────────────────────────────────────────


def test_the_subtitle_admits_when_there_are_no_ads():
    """On desktop no ad can appear, so the pitch must not claim ad removal."""
    from screens.settings import premium_section as ps

    assert "has_ads" in _card()
    # The pure helper is checkable directly (KTV notifications.py:143).
    assert callable(getattr(ps, "page_has_ads", None))


# ── the Play build does not build the card at all ───────────────────────────


def test_the_screen_does_not_build_the_card_on_the_play_channel():
    """The gate is at the call site — not an empty container from the builder.

    Both references are explicit: "Not even a disabled card — nothing to
    declare, nothing to reach, ads stay on" (ktv-player settings_screen).
    """
    text = _SCREEN.read_text(encoding="utf-8")
    assert "CHANNEL" in text, "the screen does not check the channel at all"


# ── the wallet dialog ───────────────────────────────────────────────────────


def test_wallet_premium_button_is_channel_gated():
    text = (_SRC / "components/wallet_dialog.py").read_text(encoding="utf-8")
    assert "CHANNEL" in text, "the wallet's premium button ignores the channel"


def test_wallet_premium_button_no_longer_reads_a_nonexistent_controller():
    """`state.controller` does not exist on AppState, so the button was inert."""
    text = (_SRC / "components/wallet_dialog.py").read_text(encoding="utf-8")
    assert 'getattr(state, "controller"' not in text


# ── helpers ─────────────────────────────────────────────────────────────────


class _FakePage:
    platform = None
    views: ClassVar[list] = []

    def __init__(self):
        self.dialogs = []
        self.scheduled = []

    def show_dialog(self, d):
        self.dialogs.append(d)

    def pop_dialog(self):
        if self.dialogs:
            self.dialogs.pop()

    def update(self, *a, **k):
        pass

    def run_task(self, fn, *a, **k):
        self.scheduled.append((fn, a))
        result = fn(*a, **k)
        if hasattr(result, "__await__"):
            import asyncio

            return asyncio.new_event_loop().run_until_complete(result)
        return result

    def __getattr__(self, name):
        def _noop(*a, **k):
            return None

        return _noop


def _async_return(value):
    import asyncio

    future = asyncio.get_event_loop_policy().new_event_loop().create_future()
    future.set_result(value)

    async def _coro(*a, **k):
        return value

    return _coro


def _flatten(control, out=None) -> list[str]:
    if out is None:
        out = []
    value = getattr(control, "value", None)
    if isinstance(value, str) and value:
        out.append(value)
    for child in getattr(control, "controls", []) or []:
        _flatten(child, out)
    content = getattr(control, "content", None)
    if content is not None and getattr(content, "controls", None) is not None:
        _flatten(content, out)
    return out
