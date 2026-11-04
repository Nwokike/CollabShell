# Audit: session-store filelock crash, prune-on-error, keepalive gap (from user's flet-run log, 2026-11-03)

Log evidence: 12:51:39 `RuntimeError: Cannot acquire write lock on
.flet/storage/data/colab-cli/sessions.json.lock ... while it is held by thread ...` at
`session_ops.py:316 st.store.remove(...)`, then "0 listed, 1 absent local records removed"
(local session pruned). Earlier: ~23 min (12:28→12:51) with a session listed and NO keep-alive
execs. Exit-time Flutter warnings (FlutterEngineRemoveView, FlBinaryMessenger) = benign teardown noise.

## 1. Root cause of the RuntimeError
- `_cli_state()` (session_ops.py:30-52) caches ONE `colab_cli.State` → one `StateStore` → one
  `filelock.ReadWriteLock` object (`colab_cli/state.py:49-59`, created with `is_singleton=False`
  precisely so that *distinct* store instances serialize via the OS file lock).
- All colab impls run in `asyncio.to_thread` worker threads and share that singleton, so two threads
  hit the SAME ReadWriteLock object; filelock pins a write lock to the acquiring thread and raises
  `RuntimeError` in `_validate_reentrant` (`filelock/_read_write.py:1061-1083`) on cross-thread
  contention. Per-call `State()` was safe because each call got its own lock object.

## 2. Fix: serialize store access in-process, keep the singleton
```python
# session_ops.py
import threading
_STORE_MUTEX = threading.Lock()
def _store_call(fn, *a, **k):
    with _STORE_MUTEX:
        return fn(*a, **k)
def _store_remove(st, name) -> bool:
    """Never raises; on lock/OS error the local record is KEPT."""
    try:
        with _STORE_MUTEX:
            st.store.remove(name)
        return True
    except Exception:
        logger.exception("store.remove(%s) failed; keeping local record", name)
        return False
```
Wrap every `st.store.*` call site (session_ops.py:86,200,271,281,316,352,362,383,392,445,469,473;
execution.py:134,138,184,421; `__init__.py:299`) in `_store_call`/`_store_remove`.
OS file lock still guards cross-process use. (threading.Lock is correct: ops run on to_thread workers.)

## 3. Never prune on error
- `_list` prune loop: use `_store_remove` (lock failure → record kept, no SessionListError-driven wipe).
- `load_session_fresh` / `_refresh_runtime_token_sync`: remove only on server-confirmed absence.
- Render `SessionListError.last_known_sessions` as UNVERIFIED instead of clearing the UI.

## 4. Keepalive gap
`keepalive.py` keys on `state.active_session_name` only — a session merely LISTED on Home
(`state.active_sessions`) is never pinged, so the VM was idle-pruned during the 23-min window.
Fix: fall back to first listed session name; log exec failures at WARNING with a consecutive-failure
counter; keep the list_sessions re-sync on failure.

## 5. pyproject parity vs proot-distro
- `legacy_packaging = true` already present. Missing vs proot-distro: `split_per_abi`, `res_dir`,
  permissions FOREGROUND_SERVICE / FOREGROUND_SERVICE_SPECIAL_USE / POST_NOTIFICATIONS,
  `[tool.flet.android.service."...ForegroundService"]` block, SPECIAL_USE meta_data. (x86_64 stays
  dropped deliberately: pyzmq 16KB ELF alignment.)

## 6. Findings
| # | Severity | Location | Finding | Fix |
|---|---|---|---|---|
| 1 | critical | session_ops.py:316 + `_cli_state` | shared ReadWriteLock contended across to_thread threads → RuntimeError | _STORE_MUTEX around all store ops |
| 2 | critical | same | lock error can prune a live session ("absent local records removed") | _store_remove never-raises guard |
| 3 | high | keepalive.py:60 | listed-but-unopened sessions never kept alive | key on active_sessions w/ fallback |
| 4 | medium | keepalive.py:71-78 | failures logged DEBUG, invisible | WARNING + failure counter |
| 5 | high | _list except path | failed check wipes UI to "0 listed" | render last_known_sessions unverified |
| 6 | low | pyproject | missing android FGS/notification settings | add per research-06 |
| 7 | info | exit | Flutter teardown warnings | benign, exit-only |
