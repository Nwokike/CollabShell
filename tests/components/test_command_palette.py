"""Command palette tests.

The properties that matter:

* **Filtering matches labels and hints**, so "explain" finds a command whose
  label does not contain the word.
* **A palette command can never crash the shell.** A raising action is caught
  and surfaced as a notice — a palette is a menu, not a code path.
* **Empty input returns everything**, so opening the palette shows the whole
  list rather than an empty screen.
"""

import sys
from pathlib import Path

import flet as ft

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from components.command_palette import open_command_palette


class FakePage:
    def __init__(self):
        self.dialogs = []

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        return self.dialogs.pop() if self.dialogs else None


def _commands():
    """(ran, commands) where `ran` collects the labels of fired actions."""
    ran = []

    def make(label, icon=ft.Icons.CHEVRON_RIGHT_ROUNDED, hint=""):
        def action():
            ran.append(label)

        return (label, icon, hint, action)

    cmds = [
        make("Open Assistant", ft.Icons.AUTO_AWESOME_OUTLINED, "Chat with the assistant"),
        make("Explain Terminal with AI", ft.Icons.AUTO_AWESOME_OUTLINED,
             "What the terminal is telling you"),
        make("Go to Home", ft.Icons.HOME_ROUNDED, "Ctrl+1"),
        make("Toggle theme", ft.Icons.BRIGHTNESS_6_ROUNDED, "Light / dark / system"),
    ]
    return ran, cmds


def _open(page, commands):
    open_command_palette(page, commands)
    return page.dialogs[-1]


def _body(dialog):
    """The KeyboardListener wrapping the filter + results."""
    return dialog.content.content


def _field(dialog):
    return _body(dialog).content.controls[0]


def _rows(dialog):
    """The result rows, minus the empty-state container."""
    return [
        c
        for c in _body(dialog).content.controls[-1].controls
        if isinstance(c, ft.Container)
    ]


class _Ev:
    """Minimal event stand-in: `key` for keys, `control.value` for changes."""

    def __init__(self, key="", value=""):
        self.key = key
        self.control = type("C", (), {"value": value})()


# ── filtering ────────────────────────────────────────────────────────────────


def test_empty_filter_shows_everything():
    page = FakePage()
    _ran, cmds = _commands()
    dialog = _open(page, cmds)
    assert len(_rows(dialog)) == len(cmds)


def test_filter_matches_the_label():
    page = FakePage()
    _ran, cmds = _commands()
    dialog = _open(page, cmds)
    field = _field(dialog)
    field.on_change(_Ev(value="assistant"))
    # Both "Open Assistant" and "Explain Terminal with AI" carry the hint.
    assert len(_rows(dialog)) == 1
    label = _rows(dialog)[0].content.controls[1].controls[0]
    assert label.value == "Open Assistant"


def test_filter_matches_a_hint_whose_label_does_not_contain_the_word():
    """'explain' must find the terminal action — its label does say it, but the
    hint is what makes it discoverable as 'what is the terminal telling me'."""
    page = FakePage()
    _ran, cmds = _commands()
    dialog = _open(page, cmds)
    field = _field(dialog)
    field.on_change(_Ev(value="terminal"))
    assert len(_rows(dialog)) == 1


def test_no_match_shows_the_empty_state():
    page = FakePage()
    _ran, cmds = _commands()
    dialog = _open(page, cmds)
    field = _field(dialog)
    field.on_change(_Ev(value="zzzz"))
    rows = _rows(dialog)
    assert len(rows) == 1
    assert isinstance(rows[0].content, ft.Text)


# ── running a command ───────────────────────────────────────────────────────


def test_clicking_a_row_runs_it_and_closes():
    page = FakePage()
    ran, cmds = _commands()
    dialog = _open(page, cmds)
    _rows(dialog)[0].on_click(None)
    assert ran == ["Open Assistant"], "the picked command must run"
    assert page.dialogs == [], "the palette must close before the action runs"


def test_enter_runs_the_selected_command():
    page = FakePage()
    ran, cmds = _commands()
    dialog = _open(page, cmds)
    _body(dialog).on_key_down(_Ev(key="Enter"))
    assert ran == ["Open Assistant"]


def test_arrow_down_moves_the_selection_and_enter_runs_the_second():
    page = FakePage()
    ran, cmds = _commands()
    dialog = _open(page, cmds)
    _body(dialog).on_key_down(_Ev(key="ArrowDown"))
    _body(dialog).on_key_down(_Ev(key="Enter"))
    assert ran == ["Explain Terminal with AI"], ran


def test_escape_closes_without_running():
    page = FakePage()
    ran, cmds = _commands()
    dialog = _open(page, cmds)
    _body(dialog).on_key_down(_Ev(key="Escape"))
    assert ran == []
    assert page.dialogs == []


def test_a_raising_action_is_caught_and_does_not_crash():
    """A palette entry is a menu, not a code path — one bad command must not
    take the shell with it."""
    page = FakePage()
    notices = []
    from core import notifications

    notifications.show_notification = lambda p, m, is_error=False: notices.append(m)
    open_command_palette(
        page, [("Boom", ft.Icons.WARNING_ROUNDED, "", lambda: 1 / 0)]
    )
    _rows(page.dialogs[-1])[0].on_click(None)
    assert notices == ["That action failed."]


# ── degenerate input ────────────────────────────────────────────────────────


def test_no_commands_is_a_no_op():
    page = FakePage()
    open_command_palette(page, [])
    open_command_palette(page, None)
    assert page.dialogs == []


def test_blank_commands_are_dropped():
    """A `(None, ...)` entry would crash the filter, so it never reaches one."""
    page = FakePage()
    page_ = FakePage()
    open_command_palette(page, [("", None, "", lambda: None), (None, None, "", None)])
    assert page.dialogs == []
    open_command_palette(page_, [("Real", ft.Icons.ADD_ROUNDED, "", lambda: None)])
    assert len(page_.dialogs) == 1
