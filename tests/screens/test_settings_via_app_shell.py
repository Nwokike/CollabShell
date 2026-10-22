"""Reproduce the owner's failure: render the REAL AppShell with Settings open.

This is the test that did not exist, and its absence is why a commit that
claimed to fix the Settings screen left it broken: `db70e6b` and `4277974`
both described this exact symptom, and the suite passed throughout.

`src/app_shell.py:565` builds the Settings screen as

    screen = SettingsScreen(key=ft.ValueKey("settings_tab"))

and `@ft.component` is the only thing that pops `key`
(`flet/components/component_decorator.py:26`). `4277974` deleted the
decorator from `SettingsScreen` while fixing something else, so the call
raised `TypeError: SettingsScreen() got an unexpected keyword argument
'key'` inside AppShell's body. That escaped into the session's update loop
(`flet/messaging/session.py:718-720`), which has no handler around
`control.update()`, so the scheduler task died and every later update was
silently dropped -- the tab switched, the content never followed, nothing
was logged.

No test renders `AppShell`, and `settings_harness.render_screen` calls
`SettingsScreen()` with no arguments, so the suite stayed green.

This renders the real `AppShell` at `current_tab == 4` and fails if anything
on that path raises.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from tests.screens.settings_harness import FakePage, app_state, texts_of


def _shell_inputs(page, state, services):
    """The three contexts `main.py` pushes around `AppShell`."""
    from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx
    from state.controller_ctx import ControllerMethods

    renderer_inputs = (
        (AppStateCtx, state),
        (ControllerMethodsCtx, ControllerMethods()),
        (ServiceCtx, services),
    )
    return renderer_inputs


def _render_app_shell(state, services, page):
    """Render the whole tree the way the session does.

    `AppShell`'s body returns a column of components, so rendering it means
    walking every nested `Component` and calling `before_update()` on each --
    exactly what `session.patch_control` does as it emits a patch. One level is
    not enough, and it matters here: `app_shell.py:565` builds the Settings
    screen inside AppShell's body, so that is the frame that raises.
    """
    from unittest import mock

    import flet as ft
    from flet.components.component import Component, Renderer

    from app_shell import AppShell

    renderer = Renderer()
    for ctx, value in _shell_inputs(page, state, services):
        renderer.push_context(ctx._key, value)

    def walk(node):
        if isinstance(node, Component):
            node.before_update()
            walk(node._b)

    with mock.patch.object(
        type(ft.context), "page", mock.PropertyMock(return_value=page)
    ):
        node = renderer.render(AppShell)
        walk(node)
    return node


@pytest.fixture
def shell():
    page = FakePage()
    page.views = [NS(navigation_bar=None, floating_action_button=None)]
    # Authenticated and onboarded: otherwise the shell renders OnboardingScreen
    # instead of the Settings tab this test is about.
    state = app_state(current_tab=4, is_authenticated=True)
    services = NS(storage=None, colab=None, credits=None, premium=None, notify=None)
    return page, state, services


def test_the_settings_tab_renders_through_the_real_app_shell(shell):
    """THE regression test: tab 4, real shell, real call site with `key=`."""
    page, state, services = shell
    node = _render_app_shell(state, services, page)

    body = node._b
    assert body is not None, "AppShell rendered nothing"
    texts = texts_of(body)
    assert "Settings" in texts or "APPEARANCE" in texts, texts[:20]


def test_the_settings_screen_is_a_component():
    """The contract the call site depends on: `key=` must be accepted.

    `@ft.component` is what pops `key` (`flet/components/component_decorator.py:26`).
    Without it `SettingsScreen` is a plain function and `app_shell.py:565`
    raises `TypeError: got an unexpected keyword argument 'key'`.
    """
    import flet as ft
    from unittest import mock

    from screens.settings import SettingsScreen

    assert getattr(SettingsScreen, "__is_component__", False), (
        "SettingsScreen must stay a @ft.component: app_shell.py:565 calls it "
        "with key=ft.ValueKey(...) and only the decorator pops that keyword"
    )

    # And the call itself must not raise -- `inspect.signature` follows
    # `__wrapped__` back to the undecorated `() -> Control`, so the only way to
    # know `key=` is accepted is to pass it.
    from flet.components.component import Renderer

    from tests.screens.settings_harness import app_state
    from state import AppStateCtx, ServiceCtx

    page = FakePage()
    renderer = Renderer()
    renderer.push_context(AppStateCtx._key, app_state(current_tab=4))
    renderer.push_context(ServiceCtx._key, NS())
    with mock.patch.object(
        type(ft.context), "page", mock.PropertyMock(return_value=page)
    ):
        node = renderer.render(lambda: SettingsScreen(key=ft.ValueKey("settings_tab")))
        assert node is not None


def test_every_screen_app_shell_builds_is_a_component():
    """The same contract for every screen the shell switches between."""
    import inspect

    import flet as ft

    from screens.files import FilesScreen
    from screens.history import HistoryScreen
    from screens.home import HomeScreen
    from screens.session_selector import SessionSelectorTab
    from screens.settings import SettingsScreen

    for screen in (
        HomeScreen,
        SessionSelectorTab,
        FilesScreen,
        HistoryScreen,
        SettingsScreen,
    ):
        assert getattr(screen, "__is_component__", False), (
            f"{screen.__name__} must be a @ft.component — the shell calls each "
            "with key=ft.ValueKey(...)"
        )
