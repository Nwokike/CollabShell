"""Assistant conversations — app-wide persistence.

Ported from DDGS's conversation_service, which is the shape the owner already
ships. The important properties, all pinned by tests:

* **One transcript per conversation**, projected to flat `{"role","content"}`
  pairs for both disk and the model. Visual extras (step rows, cards, receipts)
  are never persisted — an reopened chat renders the conversation honestly
  rather than fabricating tool detail it does not have.
* **Tombstones** for 60s after a delete, so a save already in flight when the
  user deletes a chat cannot rewrite the file and resurrect it after restart.
* **Atomic writes** with a unique temp name per attempt — a fixed
  ``.json.tmp`` collided on Windows and lost the conversation.
* Caps enforced *at save time*, not just in the UI: 400 messages per chat,
  50 chats, oldest pruned, the active chat never pruned.

Conversations live under ``resolve_storage_dir()/conversations`` — the durable
`FLET_APP_STORAGE_DATA` root that already holds notebooks, sessions and history
(see .flet/README.md: data survives updates and is the process cwd; cache may
be purged and on Android temp *is* cache, so neither is acceptable here).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

logger = logging.getLogger("conversation_service")

CONVERSATIONS_DIRNAME = "conversations"
MAX_CONVERSATIONS = 50
CONVERSATION_MESSAGE_CAP = 400
TITLE_LENGTH = 48
SCHEMA = 1
_TOMBSTONE_TTL = 60.0

_tombstones: dict[str, float] = {}


def _is_safe_id(conversation_id: str) -> bool:
    """Only [A-Za-z0-9_-] survives into a filename."""
    return bool(conversation_id) and all(
        ch.isalnum() or ch in "_-" for ch in str(conversation_id)
    )


def conversations_dir() -> Path:
    from core.storage_patch import resolve_storage_dir

    return Path(resolve_storage_dir()) / CONVERSATIONS_DIRNAME


def _path(conversation_id: str) -> Path:
    safe = "".join(ch for ch in str(conversation_id) if ch.isalnum() or ch in "_-")
    return conversations_dir() / f"{safe}.json"


def _title_from_messages(messages: list[dict]) -> str:
    for message in messages or []:
        if isinstance(message, dict) and message.get("role") == "user":
            text = str(message.get("content") or "").strip()
            if text:
                return " ".join(text.split())[:TITLE_LENGTH]
    return "New chat"


def flat_from_turns(turns: list[dict]) -> list[dict]:
    """Project a rendered transcript into the flat pairs that are stored.

    Only user/assistant text survives; step rows, cards and receipts are
    visual extras that are not in the saved format by design.
    """
    flat: list[dict] = []
    for turn in turns or []:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        if role not in ("user", "assistant"):
            continue
        text = turn.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        flat.append({"role": role, "content": text})
    return flat


def new_conversation_id() -> str:
    return uuid.uuid4().hex[:12]


def ensure_active() -> str:
    from core.state import state

    cid = getattr(state, "active_assistant_conversation", "") or ""
    if not _is_safe_id(cid):
        cid = new_conversation_id()
        state.active_assistant_conversation = cid
    return cid


def refresh_state() -> list[dict]:
    from core.state import state

    rows = list_conversations()
    state.assistant_conversations = rows
    return rows


def _prune_tombstones(now: float | None = None) -> None:
    now = time.time() if now is None else now
    for cid in [c for c, ts in _tombstones.items() if now - ts > _TOMBSTONE_TTL]:
        _tombstones.pop(cid, None)


def _read(path: Path) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except ValueError, TypeError:
        logger.debug("unreadable conversation file: %s", path.name)
        return None
    return payload if isinstance(payload, dict) else None


def _write(path: Path, payload: dict) -> bool:
    """Write atomically; two saves racing must not fight over one file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("conversation write failed (%s): %s", path.name, exc)
        return False
    text = json.dumps(payload, ensure_ascii=False)
    for attempt in range(3):
        tmp = path.with_name(f"{path.stem}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
            return True
        except (OSError, ValueError, TypeError) as exc:
            try:
                tmp.unlink()
            except OSError:
                pass
            if attempt == 2:
                logger.warning("conversation write failed (%s): %s", path.name, exc)
                return False
            time.sleep(0.05 * (attempt + 1))
    return False


def list_conversations() -> list[dict]:
    """Saved chats, newest first. Never raises."""
    try:
        directory = conversations_dir()
        if not directory.exists():
            return []
        rows = []
        for path in directory.glob("*.json"):
            payload = _read(path)
            if not payload:
                continue
            updated = payload.get("updated") or path.stat().st_mtime
            rows.append(
                {
                    "id": str(payload.get("id") or path.stem),
                    "title": str(payload.get("title") or "New chat"),
                    "updated": float(updated or 0),
                    "message_count": len(payload.get("messages") or []),
                }
            )
        rows.sort(key=lambda r: r["updated"], reverse=True)
        return rows
    except Exception:
        logger.debug("list_conversations failed", exc_info=True)
        return []


def load_conversation(conversation_id: str) -> dict | None:
    if not _is_safe_id(conversation_id):
        return None
    return _read(_path(conversation_id))


def save_conversation(
    conversation_id: str, messages: list[dict], *, title: str | None = None
) -> bool:
    if not _is_safe_id(conversation_id):
        return False
    now = time.time()
    _prune_tombstones(now)
    if conversation_id in _tombstones:
        logger.debug("refusing to save %s: it was just deleted", conversation_id)
        return False
    if not messages:
        return delete_conversation(conversation_id)

    path = _path(conversation_id)
    existing = _read(path) or {}
    payload = {
        "schema": SCHEMA,
        "id": conversation_id,
        "title": title or existing.get("title") or _title_from_messages(messages),
        "created": existing.get("created") or now,
        "updated": now,
        "messages": list(messages)[-CONVERSATION_MESSAGE_CAP:],
    }
    if not _write(path, payload):
        return False
    prune_conversations(protect=conversation_id)
    return True


def restore_conversation(
    conversation_id: str, messages: list[dict], *, title: str | None = None
) -> bool:
    """Undo a delete: clears the tombstone, then saves."""
    _tombstones.pop(conversation_id, None)
    return save_conversation(conversation_id, messages, title=title)


def prune_conversations(limit: int = MAX_CONVERSATIONS, *, protect: str = "") -> int:
    from core.state import state

    try:
        rows = list_conversations()
        if len(rows) <= limit:
            return 0
        active = getattr(state, "active_assistant_conversation", "") or ""
        doomed = [r for r in rows[limit:] if r["id"] not in (protect, active)]
        removed = 0
        for row in doomed:
            if delete_conversation(row["id"]):
                removed += 1
        return removed
    except Exception:
        logger.debug("prune_conversations failed", exc_info=True)
        return 0


def delete_conversation(conversation_id: str) -> bool:
    if not _is_safe_id(conversation_id):
        return False
    _tombstones[conversation_id] = time.time()
    try:
        _path(conversation_id).unlink(missing_ok=True)
        return True
    except OSError as exc:
        logger.warning("delete_conversation failed: %s", exc)
        return False


def delete_all() -> tuple[int, int]:
    rows = list_conversations()
    deleted = failed = 0
    for row in rows:
        if delete_conversation(row["id"]):
            deleted += 1
        else:
            failed += 1
    return deleted, failed


def model_history(conversation_id: str, limit: int = 30) -> list[dict]:
    """The flat message list handed to the model, newest last."""
    payload = load_conversation(conversation_id) or {}
    messages = payload.get("messages") or []
    return [m for m in messages if isinstance(m, dict)][-limit:]


def relative_time(timestamp: float) -> str:
    delta = max(0, time.time() - float(timestamp or 0))
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    if delta < 7 * 86400:
        return f"{int(delta // 86400)}d ago"
    return time.strftime("%b %d", time.localtime(float(timestamp or 0)))


def summarize(item: dict) -> str:
    count = int(item.get("message_count") or 0)
    noun = "message" if count == 1 else "messages"
    return f"{count} {noun} · {relative_time(item.get('updated') or 0)}"
