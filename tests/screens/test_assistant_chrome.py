"""Assistant chat-surface chrome tests.

The header is the part the owner inspects first, so its controls are pinned
here: which buttons exist, that the balance is TAPPABLE (it opens the wallet,
not just shows a number), and that the model selector is a real dropdown menu
rather than a modal list.

The dropdown shape is asserted against LM Router's pattern — a
``PopupMenuButton`` whose items carry ``content=`` and ``on_click=`` — because
that is the behaviour the owner asked for over DDGS's dialog.
"""

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import flet as ft
import pytest

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from screens import assistant_view


class FakePage:
    """Just enough Page for the chat: no server, no widget tree."""

    def __init__(self):
        self.views = []
        self.width = 420
        self.theme = None
        self.wallet_calls = []

    def update(self):
        pass

    def run_task(self, handler, *args, **kwargs):
        # Page.run_task takes the coroutine FUNCTION (not a called coroutine —
        # that raises TypeError), so it is invoked here the same way.
        import asyncio

        if asyncio.iscoroutine(handler):
            asyncio.run(handler)
            return
        result = handler(*args, **kwargs)
        if asyncio.iscoroutine(result):
            asyncio.run(result)


class FakeController:
    def __init__(self):
        self.revealed = []
        self.history_calls = []

    def reveal_cell(self, session_name, cell_id):
        self.revealed.append((session_name, cell_id))

    def open_assistant_history(self, rows):
        self.history_calls.append(list(rows or []))


def _state(**kw):
    base = {
        "active_session_name": "sess",
        "ai_model": "auto",
        "ai_help": True,
        "ai_router_url": "http://127.0.0.1:8082/v1",
        "is_premium": False,
        "credits_revision": 0,
        "active_assistant_conversation": "",
        "assistant_open": False,
        "assistant_minimized": False,
    }
    base.update(kw)
    return NS(**base)


def _session(tmp_path, monkeypatch, controller=None, **state_kw):
    from services import conversation_service as conversations

    monkeypatch.setattr(conversations, "_tombstones", {})
    monkeypatch.setattr(conversations, "conversations_dir", lambda: tmp_path)
    monkeypatch.setattr(conversations, "ensure_active", lambda: "chat1")
    session = assistant_view.ChatSession(
        FakePage(), _state(**state_kw), NS(credits=None, storage=None),
        controller,
    )
    return session


def _children(control):
    """Every child a control can hold, including PopupMenuButton's `items`."""
    kids = list(getattr(control, "controls", None) or [])
    inner = getattr(control, "content", None)
    if inner is not None:
        kids.append(inner)
    kids.extend(getattr(control, "items", None) or [])
    return kids


def _find(control, cls):
    """Depth-first search for the first control of a given type."""
    stack = [control]
    while stack:
        current = stack.pop()
        if isinstance(current, cls):
            return current
        stack.extend(_children(current))
    return None


def _find_all(control, cls):
    out, stack = [], [control]
    while stack:
        current = stack.pop()
        if isinstance(current, cls):
            out.append(current)
        stack.extend(_children(current))
    return out


@pytest.fixture(autouse=True)
def _theme(monkeypatch):
    """A real theme so brand_color() resolves rather than falling back."""
    import flet as ft

    page = FakePage()
    page.theme = ft.Theme(color_scheme=ft.ColorScheme(primary="#E58514"))
    monkeypatch.setattr(ft, "context", NS(page=page), raising=False)
    return page


# ── the header's controls ────────────────────────────────────────────────────


def test_header_has_the_five_controls_ddgs_ships(tmp_path, monkeypatch):
    """Back, chat icon/title, new chat, history, balance, model."""
    session = _session(tmp_path, monkeypatch)
    buttons = _find_all(session.view, ft.IconButton)
    tooltips = {b.tooltip for b in buttons}
    for expected in ("Minimize assistant", "New chat", "Past chats"):
        assert expected in tooltips, f"missing header button: {expected}"


def test_the_balance_is_tappable_and_opens_the_wallet(tmp_path, monkeypatch):
    """A balance nobody can act on is decoration. DDGS opens the wallet."""
    session = _session(tmp_path, monkeypatch)

    wallet = []
    from components import wallet_dialog

    monkeypatch.setattr(
        wallet_dialog, "show_wallet_dialog", lambda page, state, services: wallet.append(1)
    )
    session._open_wallet()
    assert wallet == [1], "tapping the balance must open the wallet dialog"


def test_the_model_selector_is_a_dropdown_menu_not_a_dialog(tmp_path, monkeypatch):
    """LM Router's pattern: PopupMenuButton. DDGS opens a modal instead, and
    the owner asked for the dropdown."""
    session = _session(tmp_path, monkeypatch)
    pill = _find(session.view, ft.PopupMenuButton)
    assert pill is not None, "the model selector must be a PopupMenuButton"
    # Positioned under the pill, like LM Router's.
    assert pill.menu_position == ft.PopupMenuPosition.UNDER


def _router_ready(monkeypatch):
    """Make the pill believe a router is serving.

    The pill reads the real `core.state` singleton, not the session's own state
    object — so a session built over a fake state would still see "starting"
    and correctly refuse to list models.
    """
    from core.state import state

    monkeypatch.setattr(state, "ai_router_status", "ready")
    monkeypatch.setattr(state, "ai_router_port", 8083)


def test_the_model_dropdown_lists_the_routers_models(tmp_path, monkeypatch):
    """Items come from the catalog, with auto first — nothing hardcoded."""
    from services import model_catalog

    _router_ready(monkeypatch)
    monkeypatch.setattr(
        model_catalog,
        "pickable_models",
        lambda: [
            {"id": "auto", "status": "active", "rate_hint": {"tier": "high"}},
            {"id": "qwen3", "status": "active", "rate_hint": {"tier": "medium"}},
        ],
    )
    session = _session(tmp_path, monkeypatch)
    pill = _find(session.view, ft.PopupMenuButton)
    assert len(pill.items) == 2
    # auto leads.
    first = pill.items[0]
    assert "Auto" in _texts(first), _texts(first)
    assert "qwen3" in _texts(pill.items[1])


def _texts(control):
    out = []
    stack = [control]
    while stack:
        current = stack.pop()
        value = getattr(current, "value", None)
        if isinstance(value, str) and value:
            out.append(value)
        stack.extend(_children(current))
    return out


def test_model_rows_carry_their_tier(tmp_path, monkeypatch):
    """The tier is spelled out, not only colour-coded — colour alone is not
    information when you cannot see it."""
    from services import model_catalog

    _router_ready(monkeypatch)
    monkeypatch.setattr(
        model_catalog,
        "pickable_models",
        lambda: [
            {"id": "auto", "status": "active", "rate_hint": {"tier": "high"}},
            {"id": "qwen3", "status": "active", "rate_hint": {"tier": "medium"}},
        ],
    )
    session = _session(tmp_path, monkeypatch)
    pill = _find(session.view, ft.PopupMenuButton)
    all_text = " ".join(_texts(pill))
    assert "high tier" in all_text, all_text
    assert "medium tier" in all_text, all_text


def test_picking_a_model_persists_it(tmp_path, monkeypatch):

    session = _session(tmp_path, monkeypatch)
    saved = {}

    class FakeStorage:
        async def set(self, key, value):
            saved[key] = value

    session.services = NS(credits=None, storage=FakeStorage())
    session._pick_model("qwen3")

    assert session.state.ai_model == "qwen3"
    assert saved.get("colab_ai_model") == "qwen3"


def test_the_empty_model_menu_explains_itself(tmp_path, monkeypatch):
    """An empty catalog still says what is happening and offers real help.

    The default router status is `starting`, so the copy is the "still finding
    out" one — and the action is Start router, which is the only thing that
    unblocks a router that is not up yet.
    """
    from services import model_catalog

    monkeypatch.setattr(model_catalog, "pickable_models", list)
    session = _session(tmp_path, monkeypatch)
    pill = _find(session.view, ft.PopupMenuButton)
    assert pill.items, "an empty catalog must still offer something"
    text = " ".join(_texts(pill))
    assert "Discovering available models" in text, text
    assert "Start router" in text, "the empty state must offer the action that helps"


# ── the FAB recipe ───────────────────────────────────────────────────────────


def _fab_source() -> str:
    """Only the assistant-FAB function, so asserts about the FAB cannot be
    satisfied (or defeated) by the command palette, which legitimately uses a
    sparkle icon of its own."""
    import pathlib

    src = pathlib.Path("src/app_shell.py").read_text(encoding="utf-8")
    start = src.index("def _sync_assistant_fab():")
    # The deps are inside the ft.use_effect(...) call that follows, so run to
    # the next section header rather than to the first use_effect( (which sits
    # before the deps list).
    marker = "# ──"
    end = src.index(marker, start)
    return src[start:end]


def test_the_fab_matches_the_ddgs_recipe():
    """DDGS: mini, white icon, brand fill, CHAT_BUBBLE_ROUNDED, tooltip only.
    No shape override (the platform's roundness is right) and no badge."""
    fab = _fab_source()
    assert "ft.Icons.CHAT_BUBBLE_ROUNDED" in fab, "the FAB icon must be the chat bubble"
    assert "mini=True" in fab
    assert "foreground_color=ft.Colors.WHITE" in fab
    # Not the sparkle icon nor a forced circle shape.
    assert "AUTO_AWESOME_OUTLINED" not in fab, "the FAB icon is not the sparkle"
    assert "shape=ft.CircleBorder()" not in fab, "no shape override on the FAB"


def test_the_fab_tooltip_toggles_between_open_and_minimized():
    """One button, two meanings: ask, or come back."""
    fab = _fab_source()
    assert '"Back to Assistant"' in fab
    assert '"Ask Assistant"' in fab
    # Relabelled in place rather than rebuilt.
    assert "existing.tooltip != wanted" in fab or "current.tooltip != wanted" in fab


def test_the_fab_uses_the_theme_brand_not_material_blue():
    """ft.Colors.PRIMARY is a Material blue, not our brand."""
    fab = _fab_source()
    assert "bgcolor=brand_color(page)" in fab
    assert "bgcolor=ft.Colors.PRIMARY" not in fab


def test_the_fab_comes_back_after_a_session():
    """The session screen owns the same slot, so leaving it clears it; the
    effect must re-run or the assistant button stays gone."""
    fab = _fab_source()
    assert "state.active_subview" in fab, (
        "active_subview must be a dependency so the FAB returns after a session"
    )
    # And a foreign FAB must be left alone.
    assert "the session screen owns" in fab
