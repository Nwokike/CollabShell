"""Conversation service tests: caps, tombstones, atomic write, projection.

The tombstone case is the one that matters most: a save already in flight when
the user deletes a chat must not rewrite the file and resurrect it after a
restart, which looks exactly like "delete does nothing".
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest

from services import conversation_service as cs


@pytest.fixture
def conv_dir(tmp_path, monkeypatch):
    """Point conversations at a FRESH temp dir per test, with no tombstones.

    Both are module-level and leak between tests. The tombstone leak is the
    dangerous one: every test here saves under the id "c1", so a tombstone left
    by an earlier delete test makes a later save refuse — which is the feature
    working correctly, applied to the wrong test.
    """
    directory = tmp_path / "conversations"
    monkeypatch.setattr(cs, "conversations_dir", lambda: directory)
    monkeypatch.setattr(cs, "_tombstones", {})
    return directory


def test_save_and_load_roundtrip(conv_dir):
    messages = [
        {"role": "user", "content": "load the csv"},
        {"role": "assistant", "content": "done"},
    ]
    assert cs.save_conversation("abc123", messages) is True
    payload = cs.load_conversation("abc123")
    assert payload["id"] == "abc123"
    assert payload["schema"] == 1
    assert payload["messages"] == messages
    assert payload["title"] == "load the csv"


def test_title_comes_from_the_first_user_message(conv_dir):
    cs.save_conversation("c1", [{"role": "user", "content": "  hello   there  "}])
    assert cs.load_conversation("c1")["title"] == "hello there"


def test_empty_title_falls_back(conv_dir):
    cs.save_conversation("c1", [{"role": "assistant", "content": "hi"}])
    assert cs.load_conversation("c1")["title"] == "New chat"


def test_created_survives_a_resave(conv_dir):
    cs.save_conversation("c1", [{"role": "user", "content": "one"}])
    created = cs.load_conversation("c1")["created"]
    cs.save_conversation("c1", [{"role": "user", "content": "one"}])
    assert cs.load_conversation("c1")["created"] == created


def test_message_cap_enforced_at_save(conv_dir):
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": str(i)}
        for i in range(cs.CONVERSATION_MESSAGE_CAP + 120)
    ]
    cs.save_conversation("c1", messages)
    saved = cs.load_conversation("c1")["messages"]
    assert len(saved) == cs.CONVERSATION_MESSAGE_CAP
    # The NEWEST survive, not the oldest.
    assert saved[-1]["content"] == str(cs.CONVERSATION_MESSAGE_CAP + 119)


def test_flat_projection_skips_blanks_and_unknown_roles():
    turns = [
        {"role": "user", "text": "hi"},
        {"role": "assistant", "text": "  "},
        {"role": "tool", "text": "ignored"},
        "not-a-dict",
        {"role": "assistant", "text": "answer"},
    ]
    assert cs.flat_from_turns(turns) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "answer"},
    ]


def test_delete_removes_the_file(conv_dir):
    cs.save_conversation("c1", [{"role": "user", "content": "hi"}])
    assert cs.delete_conversation("c1") is True
    assert cs.load_conversation("c1") is None


def test_tombstone_blocks_an_inflight_save(conv_dir):
    """Delete, then a save that was already running must not resurrect it."""
    cs.save_conversation("c1", [{"role": "user", "content": "hi"}])
    assert cs.delete_conversation("c1") is True
    assert cs.save_conversation("c1", [{"role": "user", "content": "hi"}]) is False
    assert cs.load_conversation("c1") is None, "a deleted chat came back"


def test_restore_clears_the_tombstone(conv_dir):
    cs.save_conversation("c1", [{"role": "user", "content": "hi"}])
    cs.delete_conversation("c1")
    messages = [{"role": "user", "content": "hi"}]
    assert cs.restore_conversation("c1", messages) is True
    assert cs.load_conversation("c1") is not None


def test_tombstone_expires(conv_dir):
    cs.save_conversation("c1", [{"role": "user", "content": "hi"}])
    cs.delete_conversation("c1")
    # Age the tombstone past its TTL.
    cs._tombstones["c1"] -= cs._TOMBSTONE_TTL + 1
    assert cs.save_conversation("c1", [{"role": "user", "content": "hi"}]) is True


def test_prune_keeps_the_active_and_protected(conv_dir, monkeypatch):
    for i in range(cs.MAX_CONVERSATIONS + 4):
        cs.save_conversation(f"c{i}", [{"role": "user", "content": f"m{i}"}])
    protected = f"c{cs.MAX_CONVERSATIONS - 1}"
    cs.prune_conversations(protect=protected)
    rows = [r["id"] for r in cs.list_conversations()]
    assert protected in rows
    assert len(rows) <= cs.MAX_CONVERSATIONS


def test_prune_keeps_the_active_conversation(conv_dir, monkeypatch):
    import core.state as state_mod

    chatbot = state_mod.state
    for i in range(cs.MAX_CONVERSATIONS + 4):
        cs.save_conversation(f"c{i}", [{"role": "user", "content": f"m{i}"}])
    active = f"c{cs.MAX_CONVERSATIONS - 1}"
    monkeypatch.setattr(chatbot, "active_assistant_conversation", active)
    cs.prune_conversations()
    assert active in [r["id"] for r in cs.list_conversations()]


def test_delete_all(conv_dir):
    cs.save_conversation("c1", [{"role": "user", "content": "a"}])
    cs.save_conversation("c2", [{"role": "user", "content": "b"}])
    deleted, failed = cs.delete_all()
    assert deleted == 2 and failed == 0
    assert cs.list_conversations() == []


def test_list_is_newest_first(conv_dir):
    import time

    cs.save_conversation("old", [{"role": "user", "content": "old"}])
    time.sleep(0.02)
    cs.save_conversation("new", [{"role": "user", "content": "new"}])
    rows = cs.list_conversations()
    assert [r["id"] for r in rows] == ["new", "old"]


def test_list_survives_an_unreadable_file(conv_dir):
    cs.save_conversation("good", [{"role": "user", "content": "ok"}])
    (conv_dir / "broken.json").write_text("{not json", encoding="utf-8")
    rows = cs.list_conversations()
    assert [r["id"] for r in rows] == ["good"]


def test_missing_dir_is_not_an_error(conv_dir):
    assert cs.list_conversations() == []
    assert cs.load_conversation("nope") is None


def test_unsafe_ids_are_rejected(conv_dir):
    """A path-shaped id must not escape the conversations directory."""
    for bad in ("../escape", "a/b", "", None, "with space"):
        assert cs.save_conversation(bad, [{"role": "user", "content": "x"}]) is False
    assert list(conv_dir.glob("*.json")) == []


def test_model_history_is_flat_and_capped(conv_dir):
    cs.save_conversation(
        "c1",
        [
            {"role": "user" if i % 2 == 0 else "assistant", "content": str(i)}
            for i in range(50)
        ],
    )
    history = cs.model_history("c1", limit=10)
    assert len(history) == 10
    assert all(set(m) == {"role", "content"} for m in history)
    assert history[-1]["content"] == "49"


def test_relative_time_and_summarize():
    import time

    now = time.time()
    assert cs.relative_time(now) == "just now"
    assert cs.relative_time(now - 120) == "2m ago"
    assert cs.relative_time(now - 7200) == "2h ago"
    assert cs.relative_time(now - 3 * 86400) == "3d ago"
    assert cs.summarize({"message_count": 1, "updated": now}) == "1 message · just now"
    assert cs.summarize({"message_count": 2, "updated": now}) == "2 messages · just now"
