"""Tests for the keyboard shortcut engine: Binding matching, router
priority/suppression, and the use_keyboard_shortcuts hook (dispatch,
chaining, cleanup) using the KTV Player mocking pattern.
"""

import asyncio
from unittest import mock

import flet.controls.context as _flet_ctx

from core.shortcuts import SUPPRESS, Binding, ShortcutRouter
from hooks.use_keyboard_shortcuts import use_keyboard_shortcuts


def _event(key, ctrl=False, shift=False, alt=False, meta=False):
    e = mock.Mock()
    e.key = key
    e.ctrl = ctrl
    e.shift = shift
    e.alt = alt
    e.meta = meta
    return e


# ── Binding ──────────────────────────────────────────────────────────────────


def test_binding_normalizes_key_labels():
    assert Binding("Arrow Up").key == "arrowup"
    assert Binding("ArrowUp").key == "arrowup"
    assert Binding("Enter").key == "enter"
    assert Binding("Return").key == "enter"
    assert Binding("Escape").key == "escape"
    assert Binding("F1").key == "f1"


def test_binding_matches_exact_modifiers():
    assert Binding("Enter", shift=True).matches(_event("Enter", shift=True))
    assert not Binding("Enter", shift=True).matches(_event("Enter"))
    # ctrl+shift+enter must not trigger the plain shift+enter binding
    assert not Binding("Enter", shift=True).matches(
        _event("Enter", ctrl=True, shift=True)
    )
    assert not Binding("Enter", ctrl=True).matches(
        _event("Enter", ctrl=True, shift=True)
    )


def test_binding_ctrl_matches_meta_for_macos():
    assert Binding("s", ctrl=True).matches(_event("s", meta=True))
    # But a plain-key binding must not fire while a modifier is held
    assert not Binding("a").matches(_event("a", ctrl=True))
    assert not Binding("a").matches(_event("a", meta=True))


def test_binding_letter_case_insensitive():
    assert Binding("s", ctrl=True).matches(_event("S", ctrl=True))


# ── Router ───────────────────────────────────────────────────────────────────


def test_router_resolves_latest_registration_first():
    router = ShortcutRouter()
    global_action = mock.Mock()
    screen_action = mock.Mock()
    router.register(lambda: [(Binding("F1"), global_action)])
    router.register(lambda: [(Binding("F1"), screen_action)])

    resolved = router.resolve(_event("F1"))
    assert resolved is screen_action  # resolve returns; the hook invokes


def test_router_suppress_stops_lower_priority_providers():
    """Terminal context owns the keyboard: nothing below it may fire."""
    router = ShortcutRouter()
    global_action = mock.Mock()
    router.register(lambda: [(Binding("1", ctrl=True), global_action)])
    router.register(lambda: SUPPRESS)  # inner context vetoes everything

    # SUPPRESS returns None AND prevents the global action from resolving
    assert router.resolve(_event("1", ctrl=True)) is None


def test_router_unregister_removes_provider():
    router = ShortcutRouter()
    action = mock.Mock()
    unregister = router.register(lambda: [(Binding("F1"), action)])
    unregister()
    assert router.resolve(_event("F1")) is None

    # Double unregister must not raise
    unregister()


def test_router_returns_none_when_no_match():
    router = ShortcutRouter()
    router.register(lambda: [(Binding("F1"), mock.Mock())])
    assert router.resolve(_event("z")) is None


# ── Hook (KTV mocking pattern) ───────────────────────────────────────────────


def _mock_context_page():
    mock_page = mock.MagicMock()
    mock_page.on_keyboard_event = None

    p = mock.patch.object(
        type(_flet_ctx.context),
        "page",
        mock.PropertyMock(return_value=mock_page),
    )
    p.start()
    return mock_page, p.stop


def _install_hook(router):
    with mock.patch("flet.on_mounted") as mock_mounted:
        use_keyboard_shortcuts(router)
        assert mock_mounted.called
        installer = mock_mounted.call_args[0][0]
        return installer()


def test_hook_dispatches_router_action():
    mock_page, cleanup = _mock_context_page()
    try:
        action = mock.MagicMock()
        router = ShortcutRouter()
        router.register(lambda: [(Binding("Enter", shift=True), action)])
        _install_hook(router)

        handler = mock_page.on_keyboard_event
        assert handler is not None

        asyncio.run(handler(_event("Enter", shift=True)))
        action.assert_called_once()
    finally:
        cleanup()


def test_hook_awaits_async_actions():
    mock_page, cleanup = _mock_context_page()
    try:
        order: list[str] = []

        async def action():
            order.append("ran")

        router = ShortcutRouter()
        router.register(lambda: [(Binding("s", ctrl=True), action)])
        _install_hook(router)

        asyncio.run(handler_run(mock_page.on_keyboard_event, _event("s", ctrl=True)))
        assert order == ["ran"]
    finally:
        cleanup()


def test_hook_chains_to_previous_handler_for_unhandled_keys():
    mock_page, cleanup = _mock_context_page()
    try:
        previous = mock.MagicMock()
        mock_page.on_keyboard_event = previous
        _install_hook(ShortcutRouter())

        asyncio.run(handler_run(mock_page.on_keyboard_event, _event("a")))
        previous.assert_called_once()
    finally:
        cleanup()


def test_hook_cleanup_restores_previous_handler():
    mock_page, cleanup = _mock_context_page()
    try:
        original = mock.MagicMock()
        mock_page.on_keyboard_event = original
        clean = _install_hook(ShortcutRouter())

        assert mock_page.on_keyboard_event is not original
        clean()
        assert mock_page.on_keyboard_event is original
    finally:
        cleanup()


def test_cleanup_on_remount_prevents_handler_nesting():
    mock_page, cleanup = _mock_context_page()
    try:
        original = mock.MagicMock()
        mock_page.on_keyboard_event = original

        clean1 = _install_hook(ShortcutRouter())
        clean1()
        _install_hook(ShortcutRouter())

        # Unmatched key must reach `original` exactly once (no chained
        # accumulation of stale handlers across remounts).
        asyncio.run(handler_run(mock_page.on_keyboard_event, _event("a")))
        original.assert_called_once()
    finally:
        cleanup()


async def handler_run(handler, event):
    await handler(event)
