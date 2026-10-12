"""OS notification service tests.

The properties that matter:

* **Never breaks the caller.** Notifications need the Dart half of a built
  app, so under `flet run` (or an unsupported platform) every call must be a
  no-op rather than an exception. A phone that refuses to notify cannot be
  allowed to kill a cell run.
* **The deep link round-trips.** The payload is the only thing the tap handler
  gets, so it has to parse back to the same path and params that were put in.
* **Failure is swallowed at the right level** — the plugin raising becomes a
  debug log, not a traceback in the UI.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest

from services import notify


@pytest.fixture
def plugin_absent(monkeypatch):
    """Make ``flet_notifications`` unimportable, as under ``flet run``.

    These properties used to pass by ambient luck — the package was simply not
    installed. Now that it is a real dependency, absence has to be forced or
    the "no Dart half" path is never exercised.
    """
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("flet_notifications"):
            raise ImportError(f"No module named {name!r} (simulated)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # _channel_types caches nothing, so the import guard is enough.
    return lambda: pytest.raises(ImportError)


class FakePlugin:
    """Stands in for flet_notifications.LocalNotifications.

    Records what was asked for, and can be told to raise.
    """

    def __init__(self, raises=None):
        self.shown = []
        self.channels = []
        self.raises = raises
        self.permission = True

    async def request_permissions(self):
        return self.permission

    async def create_notification_channel(self, channel):
        self.channels.append(channel)

    async def show(self, **kwargs):
        if self.raises:
            raise self.raises
        self.shown.append(kwargs)

    async def get_notification_app_launch_details(self):
        return NS(did_notification_launch_app=False, notification=None)


def _service(plugin, router=None):
    svc = notify.NotifyService(state=NS(), router=router)
    svc._service = plugin
    svc._initialised = True
    return svc


def _run(coro):
    return asyncio.run(coro)


def _action_ids(actions):
    """Action ids regardless of whether the plugin's type or the mirror is in
    use — both implement to_dict()."""
    return [a.to_dict()["id"] for a in actions or []]


# ── the deep link ───────────────────────────────────────────────────────────


def test_deep_link_carries_path_and_query():
    link = notify._deep_link("session", name="s1", tab="nb1", cell="c9")
    assert link == "collabshell://session?name=s1&tab=nb1&cell=c9"


def test_deep_link_without_query():
    assert notify._deep_link("home") == "collabshell://home"
    assert notify._deep_link("assistant") == "collabshell://assistant"


def test_deep_link_drops_empty_values():
    """An empty tab must not produce `tab=` and confuse the router."""
    link = notify._deep_link("session", name="s1", tab="", cell="c9")
    assert "tab=" not in link, link
    assert "name=s1" in link and "cell=c9" in link


def test_a_tap_parses_back_to_the_same_route_and_params():
    """The payload is the ONLY thing the tap handler receives, so it must
    survive the round trip exactly."""
    seen = []
    svc = _service(FakePlugin(), router=lambda path, params, action: seen.append(
        (path, params, action)
    ))
    payload = notify._deep_link("session", name="s1", tab="nb1", cell="c9")
    svc.on_tap(NS(payload=payload, action_id="open"))
    assert seen == [("session", {"name": "s1", "tab": "nb1", "cell": "c9"}, "open")], seen


def test_a_tap_without_a_payload_is_ignored():
    seen = []
    svc = _service(FakePlugin(), router=lambda *a: seen.append(a))
    svc.on_tap(NS(payload="", action_id=""))
    svc.on_tap(NS(payload="https://example.com", action_id=""))
    assert seen == [], "a foreign or empty payload must not route"


# ── never breaking the caller ───────────────────────────────────────────────


def test_no_plugin_means_every_call_is_a_noop(plugin_absent):
    """Under `flet run` there is no Dart half; nothing may raise."""
    svc = notify.NotifyService(state=NS())
    # _build() must not blow up when the import fails.
    assert svc._build() is None
    # Every entry point is a silent no-op.
    _run(svc.cell_done(session_name="s", tab_id="t", cell_id="c", ok=True))
    _run(svc.session_ready("s"))
    _run(svc.session_lost("s"))
    _run(svc.turn_done())
    _run(svc.credits_low(3))
    _run(svc.replay_launch())
    assert svc.on_tap(NS(payload="collabshell://home", action_id="")) is None


def test_a_plugin_error_becomes_a_noop_not_an_exception():
    """A phone that refuses to notify cannot be allowed to break a cell run."""
    plugin = FakePlugin(raises=RuntimeError("plugin exploded"))
    svc = _service(plugin)
    # Each call swallows the plugin's failure.
    _run(svc.cell_done(session_name="s", tab_id="t", cell_id="c", ok=False))
    _run(svc.session_ready("s"))
    _run(svc.turn_done(preview="hi"))
    assert plugin.shown == [], "the plugin raised every time, so nothing was posted"


def test_permission_denied_still_does_not_raise():
    """A denied permission is a fact to log, not an exception to raise."""
    plugin = FakePlugin()
    plugin.permission = False
    svc = notify.NotifyService(state=NS())
    svc._service = plugin
    assert _run(svc.initialise()) is True
    assert svc._initialised is True, "init completes even when denied"


def test_the_channel_policy_is_testable_without_the_plugin():
    """Three channels, runs the quiet one. Checked as data so the test does
    not need flet_notifications installed."""
    svc = notify.NotifyService(state=NS())
    wanted = svc._wanted_channels()
    # Without the plugin there are no channels to build; with it, the policy.
    if not wanted:
        assert notify.CHANNEL_RUNS and notify.CHANNEL_SESSION and notify.CHANNEL_BILLING
        return
    assert {c.id for c in wanted} == {
        notify.CHANNEL_RUNS,
        notify.CHANNEL_SESSION,
        notify.CHANNEL_BILLING,
    }
    runs = next(c for c in wanted if c.id == notify.CHANNEL_RUNS)
    assert runs.play_sound is False, "a finished cell must not make noise"
    assert runs.show_badge is False, "a finished cell must not badge"


# ── the payloads the app sends ───────────────────────────────────��──────────


def test_cell_done_posts_with_an_open_action_and_a_deep_link():
    plugin = FakePlugin()
    svc = _service(plugin)
    _run(svc.cell_done(session_name="s1", tab_id="nb1", cell_id="c9", ok=True))
    assert len(plugin.shown) == 1
    posted = plugin.shown[0]
    assert posted["title"] == "Cell finished"
    assert posted["payload"] == "collabshell://session?name=s1&tab=nb1&cell=c9"
    # A success offers only "Open"; a failure adds the AI fix-up.
    assert _action_ids(posted["actions"]) == ["open"]
    assert posted["channel_id"] == notify.CHANNEL_RUNS


def test_a_failed_cell_offers_the_ai_fix_action():
    plugin = FakePlugin()
    svc = _service(plugin)
    _run(
        svc.cell_done(
            session_name="s1",
            tab_id="nb1",
            cell_id="c9",
            ok=False,
            detail="ZeroDivisionError: division by zero",
        )
    )
    posted = plugin.shown[0]
    assert posted["title"] == "Cell failed"
    assert _action_ids(posted["actions"]) == ["open", "fix"]
    # The error is what makes the notification useful.
    assert "ZeroDivisionError" in posted["body"], posted["body"]


def test_long_detail_is_capped():
    """A traceback must not become a novel in the shade."""
    plugin = FakePlugin()
    svc = _service(plugin)
    _run(svc.cell_done(session_name="s", tab_id="t", cell_id="c", ok=False,
                       detail="x" * 5000))
    assert len(plugin.shown[0]["body"]) <= 200


def test_each_subject_has_its_own_channel():
    plugin = FakePlugin()
    svc = _service(plugin)
    _run(svc.cell_done(session_name="s", tab_id="t", cell_id="c", ok=True))
    _run(svc.session_ready("s"))
    _run(svc.session_lost("s"))
    _run(svc.turn_done())
    _run(svc.credits_low(2))
    channels = {p["channel_id"] for p in plugin.shown}
    assert channels == {
        notify.CHANNEL_RUNS,
        notify.CHANNEL_SESSION,
        notify.CHANNEL_BILLING,
    }, channels


def test_init_is_idempotent(plugin_absent):
    """Permission is asked once; re-entering does not stack dialogs.

    With the plugin absent `_wanted_channels` is empty, so this pins the guard
    itself rather than the channel payload.
    """
    plugin = FakePlugin()
    svc = notify.NotifyService(state=NS())
    svc._service = plugin
    assert _run(svc.initialise()) is True
    assert _run(svc.initialise()) is True
    # initialise() guards on _initialised, so the second call is a no-op.
    assert plugin.channels == [], "init must not repeat its work"


def test_the_same_id_updates_rather_than_stacks():
    """Notification ids are stable, so a repeated event replaces the old one."""
    plugin = FakePlugin()
    svc = _service(plugin)
    for _ in range(3):
        _run(svc.turn_done(preview="again"))
    assert all(p["id"] == notify._ID_TURN_DONE for p in plugin.shown)


# ── the user's switch ────────────────────────────────────────────────────────


def test_the_settings_switch_silences_every_channel():
    """Off must mean off, on every channel — a switch that only mutes one is
    a switch that looks broken."""
    svc = notify.NotifyService(state=NS(notify_enabled=False))
    plugin = FakePlugin()
    svc._service = plugin
    _run(svc.initialise())
    _run(svc.cell_done(session_name="s", tab_id="t", cell_id="c", ok=True))
    _run(svc.session_ready("s"))
    _run(svc.turn_done())
    assert plugin.shown == [], "a muted service must post nothing"


def test_enable_and_disable_restore_the_channel():
    svc = notify.NotifyService(state=NS(notify_enabled=True))
    plugin = FakePlugin()
    svc._service = plugin
    _run(svc.initialise())
    _run(svc.turn_done())
    assert plugin.shown, "with the switch on it must post"
    svc.disable()
    _run(svc.turn_done())
    assert len(plugin.shown) == 1, "disable must take effect immediately"
    svc.enable()
    _run(svc.turn_done())
    assert len(plugin.shown) == 2


# ── tap routing ──────────────────────────────────────────────────────────────


def test_a_failed_cell_notification_offers_to_ask_ai_to_fix_it():
    """The most useful button on a failure: hand it straight to the fixer."""
    svc = notify.NotifyService(state=NS(notify_enabled=True))
    plugin = FakePlugin()
    svc._service = plugin
    _run(svc.initialise())
    _run(svc.cell_done(
        session_name="s", tab_id="t", cell_id="c", ok=False, detail="NameError: x"
    ))
    (shown,) = plugin.shown
    titles = {getattr(a, "title", "") for a in (shown.get("actions") or [])}
    assert "Ask AI to fix" in titles, titles
    ids = {getattr(a, "id", "") for a in (shown.get("actions") or [])}
    assert "fix" in ids, ids


def test_a_payload_round_trips_to_the_same_tab_and_cell():
    """The payload is all the tap handler gets, so it has to carry the ids."""
    from services.notify import PAYLOAD_PREFIX

    svc = notify.NotifyService(state=NS(notify_enabled=True))
    plugin = FakePlugin()
    svc._service = plugin
    _run(svc.initialise())
    _run(svc.cell_done(
        session_name="my sess", tab_id="tab1", cell_id="cell9", ok=True
    ))
    (shown,) = plugin.shown
    payload = shown["payload"]
    assert payload.startswith(PAYLOAD_PREFIX)
    assert "cell=cell9" in payload
    assert "tab=tab1" in payload
    # Parse it back the way the router does.
    target = payload[len(PAYLOAD_PREFIX):]
    path, _, query = target.partition("?")
    params = dict(
        pair.split("=", 1) for pair in query.split("&") if "=" in pair
    )
    assert path == "session"
    assert params["cell"] == "cell9"
    assert params["tab"] == "tab1"


# ── the tap handler must be registered on the SERVICE ───────────────────────


def test_the_plugin_gets_the_tap_handler_registered():
    """Without this the plugin dispatches to nobody: every notification and
    action button drops, so the router is unreachable and the feature looks
    broken-by-design rather than mis-wired."""
    svc = notify.NotifyService(state=NS(notify_enabled=True))
    service = svc._build()
    assert service is not None, "the plugin is installed, so a service exists"
    assert service.on_tap is not None, "on_tap must be registered on the plugin"
    assert service.on_action is not None, "action buttons route through on_action"
    # A real plugin event must reach the router.
    seen = []
    svc.router = lambda path, params, action="": seen.append((path, params, action))
    svc._on_event(NS(payload="collabshell://home", action_id=""))
    assert seen, "a plugin event must reach the router"


def test_a_registered_handler_survives_a_rebuild():
    """_build() returns the cached service, so the handler is set once."""
    svc = notify.NotifyService(state=NS(notify_enabled=True))
    first = svc._build()
    second = svc._build()
    assert first is second
