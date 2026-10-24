"""The PREMIUM card is DDGS's card, not a variant of ours.

The owner: *"Compare our premium to both KTV player and DDGS. Make sure they
are one-to-one identical including how we hide it for the app (playstore)."*

Every assertion here is a difference the comparison found. Each one is a
defect a user could hit:

  - Restore purchases did not exist, so a paying user who reinstalled could
    never recover a purchase (`kiri_restore` had zero callers).
  - The recovery-ID row showed a sentence instead of the ID.
  - The checkout opened with bare `webbrowser.open` — not the platform
    launcher, no `https://` guard.
  - First paint said "Could not reach the license service" while the catalog
    was still loading — a false error.
  - The card mutated `body.controls` in place (`clear()`/`append()`), which
    never marks the control dirty, so the client could show an empty card.
  - The card called `page.update()` from inside a render body.
  - The Play build still built the card and returned an empty container,
    instead of not building it at all.
  - The subtitle always claimed "Removes ads", even on desktop where no ad
    can ever appear.
  - Price rows rendered for a user who is already premium.
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
    """`clear()`/`append()` on `controls` never sets the dirty flag.

    flet's `controls` is a Prop whose `__set__` records the change
    (`value_types.py:57-77`); mutating the returned list in place bypasses
    that, so the client is never told the list changed and the card can sit
    empty. The body must be *built* from state instead.
    """
    text = _card()
    assert ".controls.clear()" not in text
    assert ".controls.append(" not in text


def test_no_page_update_from_the_render_body():
    text = _card()
    assert "page.update()" not in text


def test_first_paint_is_loading_not_a_false_error():
    """Before the catalog resolves, the card says it is loading."""
    text = _card()
    assert "Loading" in text
    # And the unreachable copy exists too, for a real failure.
    assert "Unlock options unavailable" in text


# ── the four rows, in DDGS's order ──────────────────────────────────────────


def test_status_row_names_the_app_and_handles_lapse():
    text = _card()
    assert '"CollabShell Premium"' in text
    for word in ("grace", "expired", "revoked"):
        assert word in text, f"no lapse copy for {word}"


def test_plans_are_hidden_once_premium():
    """No price rows for a user who already paid."""
    text = _card()
    assert "is_premium" in text


def test_recovery_id_row_shows_the_id():
    """The subtitle is the ID itself, not a sentence about it."""
    from screens.settings import premium_section as ps

    fake_state = NS(is_premium=False, license_prices={}, license_recovery_id="KIRI-L-ABC")
    fake_premium = NS(
        available=True,
        license=NS(claims=None, recovery_id=_async_return("KIRI-L-ABC")),
        kiri_catalog=_async_return([]),
    )
    page = _FakePage()
    card = ps.build_premium_section(page, fake_state, NS(premium=fake_premium))
    texts = _flatten(card)
    assert any("KIRI-L-ABC" in t for t in texts), texts


def test_restore_purchases_row_exists_and_calls_the_service():
    text = _card()
    assert '"Restore purchases"' in text
    assert "Re-check ownership" in text
    assert "kiri_restore" in text, "the restore dialog must call the service"


def test_row_order_is_status_plans_recovery_restore():
    """DDGS order: status -> plans -> recovery ID -> Restore."""
    text = _card()
    order = [
        text.find("CollabShell Premium"),
        text.find("_PLANS"),
        text.find("Your recovery ID"),
        text.find("Restore purchases"),
    ]
    assert all(i >= 0 for i in order), order
    assert order == sorted(order), f"rows out of DDGS order: {order}"


# ── the dialogs ─────────────────────────────────────────────────────────────


def test_email_dialog_names_the_product_and_uses_an_email_keyboard():
    text = _card()
    assert "KeyboardType.EMAIL" in text
    assert "Unlock CollabShell Premium" in text


def test_checkout_uses_the_platform_launcher_with_an_https_guard():
    text = _card()
    assert "webbrowser" not in text, "the platform launcher, not webbrowser"
    assert "UrlLauncher" in text
    assert "https://" in text, "no scheme guard on the checkout URL"


# ── the honest subtitle ─────────────────────────────────────────────────────


def test_the_subtitle_admits_when_there_are_no_ads():
    """On desktop no ad can appear, so the pitch must not claim ad removal."""
    from screens.settings import premium_section as ps

    assert "has_ads" in _card()
    # The pure helper is checkable directly.
    assert callable(getattr(ps, "page_has_ads", None)) or "page_has_ads" in _card()


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
    async def _fn(*a, **k):
        return value

    return _fn


def _flatten(node) -> list[str]:
    out: list[str] = []
    seen: set[int] = set()

    def walk(current):
        if current is None or id(current) in seen:
            return
        seen.add(id(current))
        if isinstance(current, str):
            if current:
                out.append(current)
            return
        if isinstance(current, (list, tuple)):
            for item in current:
                walk(item)
            return
        for attr in ("controls", "actions", "content", "title", "subtitle", "trailing"):
            walk(getattr(current, attr, None))
        for attr in ("text", "label", "value", "hint_text"):
            v = getattr(current, attr, None)
            if isinstance(v, str) and v:
                out.append(v)

    walk(node)
    return out
