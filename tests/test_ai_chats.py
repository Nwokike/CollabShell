"""The model catalog cache and the chat list.

Two promises the user can see:

* the picker is never empty and never lies — cached models go up
  instantly, the live list replaces them, and a failure keeps the cached
  list instead of blanking it;
* chats survive a restart, each one is deletable, and the list is
  bounded so storage cannot grow forever.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from ai import catalog
from ai.chats_sheet import _when
from ai.router import AiModel, RouterUnavailable
from ai.session import MAX_CHATS, AiSession
from core import constants


class FakeStorage:
    def __init__(self, seed=None):
        self.d: dict = dict(seed or {})

    async def get(self, k, default=None):
        return self.d.get(k, default)

    async def set(self, k, v):
        self.d[k] = v

    async def remove(self, k):
        self.d.pop(k, None)


class FakeRouter:
    def __init__(self, models=None, fail=False):
        self.models = models if models is not None else [AiModel("auto"), AiModel("m1")]
        self.fail = fail
        self.calls = 0

    async def list_models(self):
        self.calls += 1
        if self.fail:
            raise RouterUnavailable("down")
        return list(self.models)

    async def close(self):
        pass


def _chat(session, chat_id):
    return next(c for c in session.chats if c["id"] == chat_id)


def _session(seed=None, models=None, fail=False):
    s = AiSession()
    s.router = FakeRouter(models, fail)
    s._storage = FakeStorage(seed)
    return s


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    path = tmp_path / "cache"
    path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(path))
    return path


# ── Catalog cache ──────────────────────────────────────────────────────


def test_cache_lands_in_the_flet_cache_dir(cache_dir):
    catalog.write_models([AiModel("auto", rate_hint="Free")])
    path = cache_dir / catalog.CACHE_FILE
    assert path.exists(), "the cache belongs in FLET_APP_STORAGE_CACHE"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert [m["id"] for m in data["models"]] == ["auto"]
    assert data["models"][0]["rate_hint"] == "Free"


def test_cache_round_trips(cache_dir):
    catalog.write_models([AiModel("auto", "Free", 120), AiModel("m1", "", None)])
    back = catalog.read_models()
    assert [m.id for m in back] == ["auto", "m1"]
    assert back[0].latency_ms == 120
    assert back[0].rate_hint == "Free"


def test_an_expired_cache_is_not_offered(cache_dir):
    catalog.write_models([AiModel("auto")])
    path = cache_dir / catalog.CACHE_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    data["saved_at"] = time.time() - catalog.CACHE_TTL_SECONDS - 1
    path.write_text(json.dumps(data), encoding="utf-8")
    assert catalog.read_models() == []


def test_a_corrupt_cache_is_ignored_not_fatal(cache_dir):
    (cache_dir / catalog.CACHE_FILE).write_text("{not json", encoding="utf-8")
    assert catalog.read_models() == []


def test_a_missing_cache_is_fine(cache_dir):
    assert catalog.read_models() == []


def test_cache_dir_follows_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(tmp_path / "c"))
    assert catalog.cache_dir() == tmp_path / "c"
    monkeypatch.delenv("FLET_APP_STORAGE_CACHE")
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "d"))
    assert catalog.cache_dir() == tmp_path / "d" / "cache"


# ── Picker states ──────────────────────────────────────────────────────


def test_cold_start_says_starting_and_then_fills(cache_dir):
    s = _session()
    asyncio.run(s.refresh_models())
    assert s.models_loading is False
    assert [m.id for m in s.models] == ["auto", "m1"]


def test_no_cache_and_no_router_means_still_starting(cache_dir):
    s = _session(fail=True)
    asyncio.run(s.refresh_models())
    assert s.models_loading is True, "the picker must not look broken"
    assert s.models == []
    assert "starting" in s.status.lower()


def test_cached_models_show_before_the_live_answer(cache_dir):
    catalog.write_models([AiModel("auto"), AiModel("cached-only")])
    s = _session(fail=True)
    asyncio.run(s.refresh_models())
    assert [m.id for m in s.models] == ["auto", "cached-only"]
    assert s.models_loading is False
    assert s.models_stale is True
    assert "last known" in s.status


def test_live_models_replace_the_cache(cache_dir):
    catalog.write_models([AiModel("stale-model")])
    s = _session(models=[AiModel("auto"), AiModel("fresh")])
    asyncio.run(s.refresh_models())
    assert [m.id for m in s.models] == ["auto", "fresh"]
    assert s.models_stale is False
    # ...and the cache is refreshed for next time.
    assert {m.id for m in catalog.read_models()} == {"auto", "fresh"}


def test_a_pinned_model_that_disappears_falls_back_to_auto(cache_dir):
    s = _session(models=[AiModel("auto")])
    s.selected_model = "retired-model"
    asyncio.run(s.refresh_models())
    assert s.selected_model == "auto"
    assert "not being served" in s.status
    assert s._storage.d[constants.STORAGE_AI_MODEL] == "auto"


def test_a_live_pinned_model_is_left_alone(cache_dir):
    s = _session(models=[AiModel("auto"), AiModel("pinned")])
    s.selected_model = "pinned"
    asyncio.run(s.refresh_models())
    assert s.selected_model == "pinned"
    assert s.status == ""


# ── Chats ──────────────────────────────────────────────────────────────


def test_legacy_single_thread_becomes_the_first_chat():
    old = json.dumps(
        [
            {"role": "user", "content": "why is my kernel dead"},
            {"role": "assistant", "content": "restart it"},
        ]
    )
    s = _session({constants.STORAGE_AI_MESSAGES: old})
    asyncio.run(s._load_chats())
    assert len(s.chats) == 1
    assert s.chats[0]["title"] == "why is my kernel dead"
    assert [m["content"] for m in s.messages] == [
        "why is my kernel dead",
        "restart it",
    ]
    # ...and it is written forward so the migration happens once.
    assert constants.STORAGE_AI_CHATS in s._storage.d


def test_a_chat_is_named_by_its_first_question():
    s = _session()
    asyncio.run(s.new_chat())
    chat_id = s.active_chat_id
    s.messages.append({"role": "user", "content": "  load  a  csv  "})
    asyncio.run(s._persist())
    assert _chat(s, chat_id)["title"] == "load a csv", "whitespace is collapsed"


def test_a_very_long_question_gets_a_short_title():
    s = _session()
    asyncio.run(s.new_chat())
    chat_id = s.active_chat_id
    s.messages.append({"role": "user", "content": "x" * 200})
    asyncio.run(s._persist())
    title = _chat(s, chat_id)["title"]
    assert len(title) <= 43
    assert title.endswith("…")


def test_new_chat_does_not_destroy_the_old_one():
    s = _session()
    asyncio.run(s._load_chats())
    s.messages.append({"role": "user", "content": "first question"})
    asyncio.run(s._persist())
    first = s.active_chat_id
    asyncio.run(s.new_chat())
    second = s.active_chat_id
    assert {first, second} == {c["id"] for c in s.chats}
    assert s.messages == []
    asyncio.run(s.switch_chat(first))
    assert [m["content"] for m in s.messages] == ["first question"]


def test_switching_saves_what_was_on_screen():
    s = _session()
    asyncio.run(s._load_chats())
    s.messages.append({"role": "user", "content": "unsaved thinking"})
    asyncio.run(s._persist())
    other = s.active_chat_id
    s.messages.append({"role": "user", "content": "second question"})
    asyncio.run(s.new_chat())
    asyncio.run(s.switch_chat(other))
    assert [m["content"] for m in s.messages] == [
        "unsaved thinking",
        "second question",
    ]


def test_deleting_a_chat_keeps_the_others():
    s = _session()
    asyncio.run(s._load_chats())
    s.messages.append({"role": "user", "content": "one"})
    asyncio.run(s.new_chat())
    s.messages.append({"role": "user", "content": "two"})
    asyncio.run(s._persist())
    doomed, keeper = s.chats[1]["id"], s.chats[0]["id"]
    asyncio.run(s.delete_chat(doomed))
    assert [c["id"] for c in s.chats] == [keeper]
    assert s.active_chat_id == keeper


def test_deleting_the_open_chat_opens_another():
    s = _session()
    asyncio.run(s._load_chats())
    s.messages.append({"role": "user", "content": "one"})
    asyncio.run(s.new_chat())
    s.messages.append({"role": "user", "content": "two"})
    asyncio.run(s._persist())
    active = s.active_chat_id
    asyncio.run(s.delete_chat(active))
    assert s.active_chat_id != active or not s.chats
    assert s.messages == [m for m in s.messages if m["content"] == "one"]


def test_deleting_the_last_chat_leaves_a_clean_sheet():
    s = _session()
    asyncio.run(s._load_chats())
    s.messages.append({"role": "user", "content": "only"})
    asyncio.run(s._persist())
    asyncio.run(s.delete_chat(s.chats[0]["id"]))
    assert s.chats == []
    assert s.messages == []


def test_the_list_is_capped_and_keeps_the_newest():
    s = _session()
    asyncio.run(s._load_chats())
    for i in range(MAX_CHATS + 5):
        s.messages.append({"role": "user", "content": f"q{i}"})
        asyncio.run(s._persist())
        asyncio.run(s.new_chat())
    assert len(s.chats) == MAX_CHATS
    titles = {c["title"] for c in s.chats}
    assert f"q{MAX_CHATS + 3}" in titles, "the newest survive"
    assert "q0" not in titles, "the oldest are dropped"


def test_chats_survive_a_restart():
    storage = FakeStorage()
    first = AiSession()
    first.router = FakeRouter()
    first._storage = storage
    asyncio.run(first._load_chats())
    first.messages.append({"role": "user", "content": "remember me"})
    asyncio.run(first._persist())
    open_id = first.active_chat_id

    second = AiSession()
    second.router = FakeRouter()
    second._storage = storage
    asyncio.run(second._load_chats())
    assert [m["content"] for m in second.messages] == ["remember me"]
    assert second.active_chat_id == open_id


def test_clearing_a_chat_leaves_the_others_alone():
    s = _session()
    asyncio.run(s._load_chats())
    s.messages.append({"role": "user", "content": "one"})
    asyncio.run(s._persist())
    other = s.active_chat_id
    asyncio.run(s.new_chat())
    s.messages.append({"role": "user", "content": "two"})
    asyncio.run(s.clear_history())
    assert s.messages == []
    assert len(s.chats) == 2
    assert _chat(s, other)["messages"], "the other chat still has its messages"


def test_switching_mid_reply_is_refused():
    s = _session()
    asyncio.run(s._load_chats())
    s.messages.append({"role": "user", "content": "one"})
    asyncio.run(s.new_chat())
    s.streaming = True
    asyncio.run(s.switch_chat(s.chats[1]["id"]))
    assert s.streaming is True
    assert len(s.chats) == 2


def test_unreadable_stored_chats_do_not_crash():
    s = _session({constants.STORAGE_AI_CHATS: "{broken"})
    asyncio.run(s._load_chats())
    assert s.chats == []


def test_a_malformed_chat_entry_is_dropped():
    mixed = json.dumps(
        [
            {"id": "a", "messages": [], "title": "ok", "updated": 1},
            {"nope": 1},
        ]
    )
    s = _session({constants.STORAGE_AI_CHATS: mixed})
    asyncio.run(s._load_chats())
    assert [c["id"] for c in s.chats] == ["a"]


# ── Chat list labels ───────────────────────────────────────────────────


def test_relative_time_reads_like_a_phone():
    now = time.time()
    assert _when(now) == "just now"
    assert _when(now - 300) == "5m ago"
    assert _when(now - 7200) == "2h ago"
    assert _when(now - 86400 * 3) == "3d ago"
    assert _when(0).endswith(
        tuple("0123456789")
        + (
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        )
    )
