"""A harness that renders the Settings screen the way flet renders it.

The hole that let the Settings crash through: every settings test built the
sections with stubs, and every stub passed `premium=None` -- which returns
early, before the line that raised. `fa5c135`'s own commit message says it:
*"Every existing test passes premium=None, which returns early before that
line, so nothing failed."*

So a section could raise on the first render of the real app, and the whole
screen went blank, with nothing in the log. This module builds the sections
with the objects `main.py` builds, and renders them through flet's own
`Renderer` so a raise surfaces here with a traceback instead of in the app.
"""

from __future__ import annotations

import asyncio
import dataclasses
import sys
from pathlib import Path
from unittest import mock

import flet as ft

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


class FakePage:
    """Enough of `ft.Page` for the settings sections.

    `run_task` runs the coroutine to completion, synchronously. A real page
    schedules it on the event loop, so an exception inside would land in the
    loop's exception handler and be logged -- here it propagates, which is the
    point: a section that schedules broken work must fail the test.
    """

    def __init__(self, platform=ft.PagePlatform.WINDOWS):
        self.platform = platform
        self.dialogs: list = []
        self.updates = 0
        self.scheduled: list = []
        self.services: list = []
        self.session = None
        self.width = 400
        self.height = 800
        self.overlay: list = []
        self.title = ""
        self.theme_mode = ft.ThemeMode.SYSTEM
        self.theme = ft.Theme()

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        if self.dialogs:
            self.dialogs.pop()

    def update(self, *args, **kwargs):
        self.updates += 1

    def run_task(self, handler, *args, **kwargs):
        self.scheduled.append((handler, args, kwargs))
        result = handler(*args, **kwargs)
        if asyncio.iscoroutine(result):
            return asyncio.run(result)
        return result

    async def window_to_front(self):
        return None

    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            return None

        return _noop


def real_services(page, state, storage=None):
    """The real service objects, wired as `main.py` wires them."""
    from services.colab import ColabService
    from services.credit_service import CreditService
    from services.premium_service import PremiumService
    from services.storage_service import StorageService
    from state.service_ctx import Services

    if storage is None:
        storage = StorageService(page)

    wanted = {
        "colab": ColabService(),
        "storage": storage,
        "ad_service": None,
        "page": page,
        "credits": CreditService(),
        "premium": PremiumService(page, state, storage),
        "notify": None,
    }
    # The bundle grew fields over time, so only pass what this version has.
    fields = {f.name for f in dataclasses.fields(Services)}
    return Services(**{k: v for k, v in wanted.items() if k in fields})


def app_state(**overrides):
    """The app state, in the shape the settings screen expects."""
    from core.state import state

    defaults = {
        "app_ready": True,
        "onboarding_done": True,
        "is_authenticated": False,
        "auth_method": "oauth2",
        "is_online": True,
        "is_premium": False,
        "ai_mode": False,
        "ai_help": True,
        "ai_model": "auto",
        "ai_router_url": "",
        "ai_thinking": "auto",
        "credits_copy": None,
        "usage_revision": 0,
        "router_status_revision": 0,
        "current_tab": 4,
        "active_subview": "",
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(state, key, value)
    return state


def render_screen(component_fn, state, services, page):
    """Render a component the way flet's session does, in-process.

    `Renderer.render(fn)` calls `fn` directly with NO component on the render
    stack (`flet/components/component.py:474`), so any hook inside the body --
    `use_context` included -- raises "Hooks must be called inside a component
    render". The real app never does this: it renders through
    `Page.render(lambda: ...Providers(..., lambda: AppShell()))`, and each
    component's body is rendered later by `before_update()`, which pushes that
    component onto the stack (`component.py:194`).

    So this renders a thin wrapper component and then walks the tree calling
    ``before_update()`` on every node, which is exactly what
    ``session.patch_control`` does when it emits a patch.

    The wrapper calls ``component_fn(key=ft.ValueKey(...))`` the way the real
    shell does. This is deliberate: an earlier version called it with no
    arguments, and a commit that deleted ``@ft.component`` from the Settings
    screen passed here while the app's Settings tab was dead, because only
    ``@ft.component`` pops ``key``.
    """
    from flet.components.component import Renderer

    from state import AppStateCtx, ServiceCtx

    @ft.component
    def _Root():
        return component_fn(key=ft.ValueKey("settings_tab"))

    renderer = Renderer()
    # `create_context` keys the renderer's stack on the provider's private
    # `_key` (flet/components/hooks/use_context.py:57-64). Pushing the provider
    # itself would register a key nothing reads, and the screen would silently
    # fall back to the default `Services()`.
    renderer.push_context(AppStateCtx._key, state)
    renderer.push_context(ServiceCtx._key, services)
    with mock.patch.object(
        type(ft.context), "page", mock.PropertyMock(return_value=page)
    ):
        node = renderer.render(_Root)
        _render_tree(node)
    return node


def _render_tree(node, seen=None):
    from flet.components.component import Component

    if node is None:
        return
    if seen is None:
        seen = set()
    if id(node) in seen:
        return
    seen.add(id(node))

    if isinstance(node, Component):
        node.before_update()
        _render_tree(node._b, seen)
        return

    for attr in ("controls", "content", "actions", "leading", "trailing"):
        child = getattr(node, attr, None)
        if child is None:
            continue
        if isinstance(child, (list, tuple)):
            for item in child:
                _render_tree(item, seen)
        else:
            _render_tree(child, seen)


def render_settings(state, services, page):
    """Render the whole Settings screen and return its built column."""
    from screens.settings import SettingsScreen

    root = render_screen(SettingsScreen, state, services, page)
    # `root` is the `_Root` wrapper; `root._b` is the SettingsScreen node, and
    # `root._b._b` is the Column the screen's body returned.
    screen = root._b
    return screen._b if hasattr(screen, "_b") else screen


def sections_of(column):
    return list(getattr(column, "controls", []) or [])


def texts_of(node):
    """Every string a control tree would render."""
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
        for attr in (
            "controls",
            "actions",
            "content",
            "title",
            "subtitle",
            "trailing",
            "leading",
        ):
            walk(getattr(current, attr, None))
        for attr in ("text", "label", "value", "hint_text"):
            value = getattr(current, attr, None)
            if isinstance(value, str) and value:
                out.append(value)

    walk(node)
    return out


__all__ = [
    "FakePage",
    "app_state",
    "real_services",
    "render_screen",
    "render_settings",
    "sections_of",
    "texts_of",
]
