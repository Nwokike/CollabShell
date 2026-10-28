"""The Settings router row shows the router's state — it has no URL box.

The owner: *"Router URL. Is it like router port like Colab shell and LM router?
Does DDGS have something like that?"*

Neither reference app has one. DDGS has no router control at all in Settings
(`components/settings/sections_ai.py` builds exactly: Assistant mode, Thinking
depth, Assistant model, Credits, What credits are for, Scheduled crawls).
lm-router has a numeric **Port** field for its own gateway
(`screens/settings_screen.py:878-891`), never a URL. Ours had a URL box that
matched neither — and it had a footgun on top of that.

**The footgun.** The box was pre-filled with the *live* URL
(`_effective_router_url` returns `router.current_url()`), and `_save_router`
stored whatever was in it. So pressing Enter after the router had auto-landed
on 8083 saved `http://127.0.0.1:8083/v1` as a permanent override, which pinned
the app to 8083 and stopped it re-probing 8082..8092. One keypress destroyed
the auto-start behaviour that `constants.py:53-54` and `main.py:597-599`
promise. Only blanking the field and pressing Enter again recovered it.

So the row now shows the address as information, the way lm-router's status
card does — status line, then the base URL in a selectable monospace line.
There is no Start button: the router starts with the app. `state.ai_router_url`
and `STORAGE_AI_ROUTER_URL` still work as an override for anything already
stored, but nothing in the UI can set one any more.
"""

from __future__ import annotations

import pathlib
import sys

_SRC = pathlib.Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _ai_section() -> str:
    return (_SRC / "screens/settings/ai_section.py").read_text(encoding="utf-8")


def test_the_router_url_field_and_its_controls_are_gone():
    text = _ai_section()
    for needle in (
        "Router URL",
        "router_field",
        "_save_router",
        "hint_text",
        "leave blank to auto-start",
    ):
        assert needle not in text, f"ai_section still has {needle!r}"


def test_the_router_row_still_names_the_router_and_the_port():
    """It stays a row, and it still tells you where the router is."""
    text = _ai_section()
    assert '"Router"' in text, "the Router row title is gone"
    # The status line already carries the port.
    assert "Running on 127.0.0.1" in text, "the status line no longer names the port"
    assert "starts automatically" in text, "the row says the router starts"


def test_the_address_is_shown_read_only():
    """The live URL is displayed, not editable."""
    text = _ai_section()
    assert "_effective_router_url" in text, "the live URL is no longer read"
    assert "ft.TextField" not in text, "a TextField is still in the assistant section"
    # No handler writes the override from the UI.
    assert "ai_router_url = url" not in text, "the UI still writes the override"


def test_the_override_still_works_for_anything_already_stored():
    """Old installs that set an override are not broken by removing the box."""
    text = (_SRC / "main.py").read_text(encoding="utf-8")
    assert "STORAGE_AI_ROUTER_URL" in text, "hydration of the override is gone"
    assert "ai_router_url" in text


# ── premium lives in one card, not a row inside the assistant card ───────────
# DDGS's Assistant settings card has exactly: assistant mode, thinking depth,
# assistant model, credits, what credits are for, scheduled crawls. KTV Player's
# premium is a standalone Settings card. Neither has a premium row inside the
# AI section — and ours was not channel-gated, so the Play build rendered
# "Assistant premium / Unavailable", declaring a purchase surface in the build
# that must show nothing premium-shaped.


def test_the_assistant_section_has_no_premium_row():
    text = (_SRC / "screens/settings/ai_section.py").read_text(encoding="utf-8")
    for needle in (
        "Assistant premium",
        "premium_row",
        "_premium_subtitle",
        "_show_premium",
        "premium_available",
        "Upgrade",
    ):
        assert needle not in text, f"the assistant section still has {needle!r}"


def test_premium_still_lives_in_the_one_card():
    """Removing the row did not remove the feature."""
    text = (_SRC / "screens/settings/premium_section.py").read_text(encoding="utf-8")
    assert "build_premium_section" in text
    assert 'CHANNEL == "play"' in text, "the card's channel gate is gone"
    # And the screen still mounts it.
    screen = (_SRC / "screens/settings/__init__.py").read_text(encoding="utf-8")
    assert "build_premium_section" in screen


def test_the_assistant_section_reads_no_premium_service():
    """The credits line may still read `state.is_premium` for the cap — that is
    a number, not a second premium surface."""
    text = (_SRC / "screens/settings/ai_section.py").read_text(encoding="utf-8")
    assert 'services, "premium"' not in text
    assert "getattr(services" in text or "getattr(state" in text
    assert "premium.available" not in text
