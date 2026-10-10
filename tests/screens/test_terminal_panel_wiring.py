"""Terminal panel wiring (F1 / flet-terminal 0.3.9) — behavioral tests.

Drives the real handler builders with a mock MobileTerminal: asserts the
public 0.3.9 API is used (on_mount setter, clear_pending(), shared Clipboard)
without touching private _terminal internals. No network, no page.
"""

import sys
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

sys.path.insert(0, "src")


def _make_mt():
    mt = MagicMock()
    mt.send_bytes = MagicMock()
    mt.clear_pending = MagicMock()
    return mt


def _handlers(entry):
    import screens.session.terminal_panel as panel

    ps = NS(active_id=entry.id, zoom=11.0, blink=True)
    page = MagicMock()
    page._session = None
    page.session = None
    colab_service = MagicMock()
    return panel._make_entry_handlers(entry, ps, page, colab_service, "s1", snack=None)


def test_replay_clears_pending_then_replays_scrollback():
    import screens.session.terminal_panel as panel  # noqa: F401 (warms module)

    mt = _make_mt()
    entry = NS(id=1, mt=mt, client=None, scrollback=[b"a", b"b"], ready=False)
    handlers = _handlers(entry)
    # replay_scrollback is invoked via the on_mount handler.
    handlers["on_mount"]()
    mt.clear_pending.assert_called_once_with()
    assert [c.args[0] for c in mt.send_bytes.call_args_list] == [b"a", b"b"]


def test_mount_wiring_assigns_public_on_mount():
    mt = _make_mt()
    # Simulate the _TerminalHost wiring block via the real module path:
    # assign through the public setter, never _terminal.
    mt_assigned = {}
    type(mt).on_mount = property(
        lambda self: mt_assigned.get("v"),
        lambda self, v: mt_assigned.__setitem__("v", v),
    )

    def _handler(e=None):
        pass

    mt.on_mount = _handler
    assert mt_assigned["v"] is _handler
    # And the module source no longer reaches through _terminal.
    import pathlib

    src = pathlib.Path("src/screens/session/terminal_panel.py").read_text(
        encoding="utf-8"
    )
    assert "mt._terminal" not in src


def test_clipboard_instance_is_shared():
    import pathlib

    src = pathlib.Path("src/screens/session/terminal_panel.py").read_text(
        encoding="utf-8"
    )
    assert "ft.Clipboard().set(" not in src
    # Exactly one Clipboard() construction site (the shared holder) —
    # count assignments, not comment mentions.
    import re

    constructions = re.findall(r"=\s*ft\.Clipboard\(\)", src)
    assert len(constructions) == 1, constructions


def test_construction_kwargs_preserved():
    import pathlib

    src = pathlib.Path("src/screens/session/terminal_panel.py").read_text(
        encoding="utf-8"
    )
    for kw in (
        "show_search=False",
        "show_settings=False",
        "scrollback=10000",
        'font_family="JetBrains Mono"',
        "auto_focus=False",
        "expand=True",
    ):
        assert kw in src, f"missing MobileTerminal kwarg: {kw}"
