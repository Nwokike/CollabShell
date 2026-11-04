# Research: Kernel/Session Liveness in Jupyter Stack & Colab Integration

**Date:** 2026-11-02  
**Scope:** jupyter_client, jupyter_kernel_client, jupyter_core, Google Colab behavior, CollabShell error handling

---

## 1. Local Source Analysis (jupyter_client / jupyter_kernel_client / jupyter_core)

### 1(a) `is_alive()` / `_async_is_alive()` Checks

| Component | File:Line | Behavior |
|-----------|-----------|----------|
| **KernelClient._async_is_alive()** | `jupyter_client/client.py:432-446` | If parent is `KernelManager`, delegates to `parent._async_is_alive()`. Otherwise uses heartbeat channel: `self._hb_channel.is_beating()`. If no heartbeat channel, naively returns `True`. |
| **KernelManager._async_is_alive()** | `jupyter_client/manager.py:783-795` | Checks `provisioner.poll()` — returns `True` if process running (`poll() is None`), `False` if exited. |
| **HBChannel.is_beating()** | `jupyter_client/channels.py:177-182` | Returns `True` iff thread alive, not paused, AND `_beating` flag set (heartbeat response received within `time_to_dead`). |
| **KernelWebSocketClient.is_alive()** | `jupyter_kernel_client/wsclient.py:1114-1122` | Uses `self._hb_channel.is_beating()` but `HBWSChannel.is_beating()` **always returns `True`** (stub/FIXME at `wsclient.py:448`). No functional heartbeat over WebSocket. |
| **KernelHttpManager.is_alive()** | `jupyter_kernel_client/manager.py:329-335` | Calls `refresh_model()` via HTTP GET `/api/kernels/{id}` — returns `True` if kernel model exists, `False` on 404. |

**Key finding:** For remote/Colab kernels, `is_alive()` is **not reliable** — the WebSocket heartbeat is a stub, and HTTP check only validates kernel object exists, not that the VM/runtime is responsive.

---

### 1(b) Heartbeat Channel

| Aspect | Details |
|--------|---------|
| **Local (ZMQ) heartbeat** | `jupyter_client/channels.py:35-167` — `HBChannel` thread sends `b"ping"` via REQ socket every `time_to_dead = 1.0s` (line 48). Waits for REP. On timeout: calls `call_handlers(since_last_heartbeat)`, recreates socket. |
| **Remote (WebSocket) heartbeat** | `jupyter_kernel_client/wsclient.py:431-453` — `HBWSChannel` is a **stub**: `is_beating()` always `True`, `pause()`/`unpause()` no-op. **No actual heartbeat sent over WebSocket.** |
| **Heartbeat timeout** | `time_to_dead = 1.0s` (hardcoded in `HBChannel`, also returned by `HBWSChannel.time_to_dead` property). |
| **Client-side detection** | Local: detects kernel death within ~1s. Remote: **no detection via heartbeat** — relies on WebSocket close or HTTP errors. |

---

### 1(c) `wait_for_ready` Semantics and Timeout

| Implementation | File:Line | Behavior |
|----------------|-----------|----------|
| **KernelClient._async_wait_for_ready()** | `jupyter_client/client.py:161-219` | 1. If not created by KernelManager, polls `_async_is_alive()` (heartbeat) until timeout. 2. Sends `kernel_info_request`, waits for `kernel_info_reply` on shell channel (1s poll intervals). 3. Verifies IOPub channel connected. 4. Flushes IOPub. Overall timeout parameter (default `inf`). Raises `RuntimeError` on kernel death or timeout. |
| **KernelWebSocketClient.wait_for_ready()** | `jupyter_kernel_client/wsclient.py:1170-1228` | Similar: waits for `is_alive()` (stub), sends `kernel_info_request`, waits for reply (1s polls), flushes IOPub. Uses `time.time()` absolute timeout. Raises `RuntimeError`/`TimeoutError`. |

**Timeout behavior:** Both use absolute deadline. Default timeout often 60s (from `start_new_kernel` in `manager.py:848`). For Colab, `REQUEST_TIMEOUT = 30s` in `jupyter_kernel_client/constants.py`.

---

### 1(d) Kernel Death Mid-Execution

| Scenario | Message Types / Errors |
|----------|------------------------|
| **Normal completion** | `status` message with `execution_state: "idle"` (client.py:595-599, wsclient.py:1102-1107) |
| **Kernel dies during execution** | `status` with `execution_state: "dead"` or `"restarting"`; `shutdown_reply`; ZMQ/WS connection errors |
| **jupyter_client detection** | `_async_execute_interactive` checks `await self._async_is_alive()` at loop start (line 205) and before reply (line 601). Raises `RuntimeError("Kernel died before replying to kernel_info")` (line 207). |
| **jupyter_kernel_client detection** | `execute_interactive` checks `self.connection_ready.is_set()` each iteration (wsclient.py:1072). Raises `RuntimeError("Connection was lost.")` on WebSocket close. |
| **HTTP 404 (runtime gone)** | `KernelHttpManager.refresh_model()` catches `HTTPError 404`, returns `None` (manager.py:178-180). `is_alive()` then returns `False`. |

---

### 1(e) jupyter_kernel_client: execute_code Streaming & Error Handling

| Aspect | Details |
|--------|---------|
| **Streaming outputs** | `KernelClient.execute()` → `execute_interactive()` with `output_hook` (client.py:287-297). Default `output_hook` (lines 24-105) normalizes messages to dicts with `output_type`: `execute_result`, `stream`, `display_data`, `error`, `clear_output`, `update_display_data`. |
| **WebSocket execute_interactive** | `wsclient.py:978-1112` — uses `_message_received` Event + queues. Polls IOPub/stdin with deadline. Calls `output_hook(msg)` for each message matching request `msg_id`. Stops on `status` idle. |
| **output_hook receives** | Full Jupyter message dict with `header`, `parent_header`, `content`, `metadata`, `buffers`. `content` varies by `msg_type` (stream: `{name, text}`, error: `{ename, evalue, traceback}`, etc.). |
| **WebSocket close** | `_on_close()` clears `connection_ready` Event (wsclient.py:1245-1251). Next `execute_interactive` iteration raises `RuntimeError("Connection was lost.")`. |
| **HTTP 404 / "session does not exist"** | `refresh_model()` returns `None` on 404 (manager.py:178-180). `is_alive()` returns `False`. `execute()` will fail on subsequent `wait_for_ready` or `is_alive` check. |
| **Reconnect logic** | `KernelWebSocketClient` accepts `reconnect_interval` parameter (default `0` = **no reconnect**). Passed to `WebSocketApp.run_forever(reconnect=...)` (wsclient.py:1280). **No application-level reconnect.** |
| **Token expiry handling** | Not in jupyter_kernel_client — handled at `google-colab-cli` layer via `State.prune_or_recover_session()` (refreshes token via `list_assignments()`). |

---

## 2. Upstream Issues & Colab Behavior

### Key GitHub Issues & PRs

| Reference | Title | Key Finding |
|-----------|-------|-------------|
| [googlecolab/google-colab-cli#106](https://github.com/googlecolab/google-colab-cli/issues/106) | Live sessions pruned after 60 min | Runtime-proxy token expires ~3600s (`tokenExpiresInSeconds`). 404/401 misclassified as "session lost", local session deleted while VM still alive. |
| [googlecolab/google-colab-cli#123](https://github.com/googlecolab/google-colab-cli/pull/123) | Refresh runtime-proxy credentials before pruning | `prune_or_recover_session()`: on 404/401, calls `list_assignments()` — if endpoint listed, adopts fresh token/url and keeps session. |
| [googlecolab/google-colab-cli#146](https://github.com/googlecolab/google-colab-cli/pull/146) | Survive runtime-proxy token expiry | Refreshes token via `list_assignments()` (returns fresh 3600s token). Persists updated credentials. Prunes only if no live assignment server-side. |
| [googlecolab/google-colab-cli#144](https://github.com/googlecolab/google-colab-cli/pull/144) | Clean up client-side keep-alive | **Client-side `/keep-alive` ping removed** (cl/982796273). "Runtimes are automatically kept alive by the backend based on kernel activities and active connections." |
| [googlecolab/google-colab-cli#185](https://github.com/googlecolab/google-colab-cli/pull/185) | Enforce --timeout as idle limit | `--timeout` is **idle threshold**, not total deadline. Streaming execution resets idle clock on each message. |
| [datalayer/jupyter-kernel-client#41](https://github.com/datalayer/jupyter-kernel-client/pull/41) | Fix interactive execution timeout spin | Fixed busy-loop when deadline expired — now raises `TimeoutError` at deadline. |
| [googlecolab/colabtools#6101](https://github.com/googlecolab/colabtools/issues/6101) | Runtime dies after 2-3h active GPU | Pro+ L4 runtime terminates unexpectedly despite active workload. Not idle timeout, not OOM. Server-side termination. |
| [aspershupadhyay/voicebox-gpu#44](https://github.com/aspershupadhyay/voicebox-gpu/pull/44) | Keep alive through kernel activity | Colab no longer honors keep-alive ping. **Kernel activity** (execute, kernel_info_request, output) keeps runtime alive. |

### Colab Runtime Liveness Rules (Server-Side)

| Aspect | Behavior |
|--------|----------|
| **Idle timeout** | Free tier: ~90 min. Pro/Pro+: up to 24h (but reports of 2-3h termination under active GPU load — colabtools#6101). |
| **What resets idle timer** | **Kernel activity only**: executing code, sending `kernel_info_request` via kernel WebSocket, kernel producing output. Opening WebSocket connection counts as "active connection". |
| **What does NOT reset timer** | WebSocket ping/pong, HTTP keep-alive, idle WebSocket without kernel activity, client-side `/keep-alive` ping (removed). |
| **Runtime-proxy token TTL** | **3600 seconds (1 hour)** — from `RuntimeProxyInfo.tokenExpiresInSeconds`. Refreshed via `list_assignments()` (returns fresh token). |
| **404/401 ambiguity** | Could mean: (a) token expired (VM alive), (b) VM truly gone, (c) network error. Must verify via `list_assignments()` before pruning. |
| **TooManyAssignmentsError (412)** | If local session pruned but VM stays alive, repeated `colab new` creates orphaned assignments until limit hit. |

---

## 3. Direct Answers

### 3(a) Which component is "in charge" of detecting a dead/idle kernel?

| Context | Primary Detector |
|---------|------------------|
| **Local kernel (jupyter_client)** | **Heartbeat thread (`HBChannel`)** — sends ping every 1s, detects death within ~1s. `is_alive()` polls process via provisioner as backup. |
| **Remote kernel (jupyter_kernel_client)** | **NO functional heartbeat** (`HBWSChannel.is_beating()` always `True`). Detection relies on: <br>• WebSocket close (`_on_close` clears `connection_ready`)<br>• HTTP 404/401 on `refresh_model()` / API calls<br>• `wait_for_ready` timeout<br>• Execution-level idle timeout in `execute_interactive` |
| **Colab specifically** | **Server-side idle tracker** (not client). Backend monitors "kernel activities and active connections". Client detects loss only via HTTP 404/401 or WebSocket close. |

**Conclusion:** For Colab, **the server is in charge**. Client has no reliable liveness probe — only reactive detection via failed requests.

---

### 3(b) Does anything in jupyter_client keep a Colab VM alive? What client-side actions reset Colab's idle timer?

**No.** Nothing in `jupyter_client` or `jupyter_kernel_client` keeps a Colab VM alive. The old client-side `/keep-alive` ping was **removed** (google-colab-cli PR #144).

**Client-side actions that DO reset Colab's idle timer** (per voicebox-gpu PR #44, google-colab-cli):

| Action | Mechanism |
|--------|-----------|
| Execute code via `execute_code` / `execute_interactive` | Kernel activity — produces IOPub messages, counts as execution |
| Send `kernel_info_request` on shell/control channels | Direct kernel WebSocket interaction (what `wait_for_ready` does) |
| Kernel produces output (stream, display_data, etc.) | Server sees kernel busy |
| Call `list_assignments()` / `refresh_session_token()` | Gets fresh runtime-proxy token (3600s), proves assignment alive |
| Open/maintain kernel WebSocket connection | Counts as "active connection" per backend |

**Actions that do NOT reset timer:** WebSocket ping, HTTP keep-alive, idle WebSocket, any client-only activity without kernel interaction.

---

### 3(c) Errors in CollabShell's colab/execution.py / terminal_client.py — Mapping & Recovery

#### execution.py Error Handling

| Location | Error Check | Current Behavior | Recommended Mapping |
|----------|-------------|------------------|---------------------|
| Lines 163-180 (preflight) | `is_terminal_error(e)` → 404/401 | Calls `_heal_runtime_token()` once, retries. If fails: raises `ValueError` "Colab could not reach this runtime (401/404)... verify runtime in Colab" | **Map 404/401 → token expiry OR runtime gone**. Heal token, retry once. If still 404 after heal → runtime truly gone → re-acquire session. |
| Lines 369-397 (`_execute_main`) | 404 check via `hasattr(e, 'response').status_code == 404` or "404"/"Not Found" in str(e) | Same: heal token once, then `RuntimeError` "Colab could not reach this runtime (404 Not Found)... preserving local record" | **Preserve local record** (correct). But should distinguish: token expiry (heal works) vs runtime gone (heal fails). |
| Line 370-375 | `is_404` detection | Checks `e.response.status_code`, `"404" in err_str`, `"Not Found" in err_str` | **Add explicit 401 check** — token expiry often returns 401. |

#### terminal_client.py Error Handling

| Location | Error Check | Current Behavior | Recommended Mapping |
|----------|-------------|------------------|---------------------|
| Lines 189-209 (`_read_loop`) | `TimeoutError` on `read_message()` (10s) | Calls `_probe_upstream()` (WS ping). If probe fails → close socket → `_reconnect_with_backoff()` | **WS ping probe is insufficient** — Colab ignores ping. Should send `kernel_info_request` or execute trivial code to test liveness. |
| Lines 207-209 | `msg is None` (WS closed by server) | Breaks → `_reconnect_with_backoff()` | **Correct** — server closed connection. Reconnect with credential refresh. |
| Lines 310-320 (`_reconnect_attempts`) | HTTP status 400-499 on reconnect | Stops retrying ("permanent error — terminal gone") | **404/401 may be token expiry** — should refresh credentials via `_refresh_cached_credentials()` before giving up. |
| Lines 97-144 (`_refresh_cached_credentials`) | Re-reads session url/token from store | Called before each reconnect attempt | **Good** — picks up refreshed token from `session_ops.refresh_session_token()`. |

#### Recommended Error → Action Mapping for CollabShell

| Error Signature | Meaning | Recovery Action |
|-----------------|---------|-----------------|
| HTTP 404 + "session does not exist" / "Not Found" | Token expired **OR** runtime gone | 1. Call `refresh_session_token()` / `list_assignments()`<br>2. If new token works → retry<br>3. If still 404 → runtime gone → re-acquire session |
| HTTP 401 (Unauthorized) | Token expired | Refresh token → retry |
| WebSocket close (1006, 1001, 1011) | Connection lost (network or server) | Reconnect with backoff, refresh credentials first |
| HTTP 412 (TooManyAssignmentsError) | Orphaned assignments | Clean up stale assignments via `list_assignments()` + delete |
| Execution idle timeout (`TimeoutError` after `--timeout`) | Idle limit reached, not death | Continue — new execution resets idle timer |
| `RuntimeError("Connection was lost.")` from jupyter_kernel_client | WebSocket closed | Reconnect flow |

---

## 4. Recommendations for CollabShell

### 4.1 Keep-Alive Strategy

**Do NOT rely on:**
- WebSocket ping/pong (Colab ignores)
- HTTP keep-alive
- `jupyter_kernel_client` heartbeat (stub)
- Periodic `is_alive()` polls (checks HTTP, not VM liveness)

**DO implement:**
1. **Periodic kernel activity** — every 30-60s during idle:
   - Send `kernel_info_request` via existing kernel WebSocket (cheap, no execution)
   - Or execute trivial code: `pass` or `1+1` (produces output, resets idle timer)
2. **Proactive token refresh** — every 45-50 min:
   - Call `session_ops.refresh_session_token()` / `list_assignments()`
   - Update cached credentials before expiry
3. **WebSocket health check** — on read timeout:
   - Don't just ping — send `kernel_info_request` on control channel
   - If that fails, full reconnect with credential refresh

### 4.2 Error Mapping & Re-Acquire Logic

```python
# Pseudo-code for error classification
def classify_colab_error(exc: Exception) -> ErrorClass:
    if isinstance(exc, HTTPError):
        if exc.response.status_code == 404:
            if "session does not exist" in exc.response.text.lower():
                return ErrorClass.RUNTIME_GONE  # or TOKEN_EXPIRED - must verify
            return ErrorClass.TOKEN_EXPIRED_OR_GONE
        if exc.response.status_code == 401:
            return ErrorClass.TOKEN_EXPIRED
        if exc.response.status_code == 412:
            return ErrorClass.TOO_MANY_ASSIGNMENTS
    if isinstance(exc, WebSocketClosedError):
        return ErrorClass.CONNECTION_LOST
    if isinstance(exc, TimeoutError) and "idle" in str(exc).lower():
        return ErrorClass.IDLE_TIMEOUT
    return ErrorClass.UNKNOWN

def handle_error(error_class: ErrorClass, session_name: str):
    match error_class:
        case ErrorClass.TOKEN_EXPIRED:
            refresh_session_token(session_name)
            retry_operation()
        case ErrorClass.TOKEN_EXPIRED_OR_GONE:
            if refresh_session_token(session_name):
                retry_operation()
            else:
                reacquire_session()
        case ErrorClass.RUNTIME_GONE:
            reacquire_session()
        case ErrorClass.CONNECTION_LOST:
            reconnect_websocket(refresh_credentials=True)
        case ErrorClass.IDLE_TIMEOUT:
            continue  # Not fatal, just start new execution
```

### 4.3 AI Assistant Access to Idle Sessions — Reconnect/Wake Strategy

For AI assistant to access even "idle" sessions:

1. **On session select/activate**: Call `refresh_session_token()` proactively
2. **Before any execution**: Ensure WebSocket connected, send `kernel_info_request` to wake
3. **If 404/401 on first attempt**: Auto-refresh token, retry once transparently
4. **Background keep-alive** (optional, for long-running assistant sessions):
   - Timer: every 45s, send `kernel_info_request` if no recent execution
   - Timer: every 50 min, refresh runtime-proxy token
5. **Graceful degradation**: If reconnect fails, show "Runtime disconnected — click to reconnect" not "Session lost"

### 4.4 Specific Code Changes for CollabShell

| File | Change |
|------|--------|
| `execution.py` | Add explicit 401 handling alongside 404. Distinguish token expiry (heal works) vs runtime gone (heal fails). |
| `terminal_client.py` | Replace WS ping probe with `kernel_info_request` on control channel. On 4xx reconnect error, refresh credentials before giving up. |
| `session_ops.py` | Ensure `refresh_session_token()` calls `list_assignments()` and updates local store atomically. |
| New: `keepalive.py` | Background task: periodic `kernel_info_request` + token refresh. Integrate with session lifecycle. |

---

## References

1. jupyter_client source: `client.py`, `manager.py`, `channels.py`, `kernelapp.py`
2. jupyter_kernel_client source: `client.py`, `wsclient.py`, `manager.py`
3. google-colab-cli issues: #106, #123, #144, #146, #147, #155, #183, #185
4. datalayer/jupyter-kernel-client PR #41
5. googlecolab/colabtools #6101
6. aspershupadhyay/voicebox-gpu PR #44
7. CollabShell: `src/services/colab/execution.py`, `terminal_client.py`, `session_ops.py`
