# Research: google-colab-cli Upstream & Idle/Session Lifecycle Analysis

**Date:** 2026-11-02  
**Installed Version:** 0.7.4 (in `.venv/lib/python3.14/site-packages/colab_cli/`)  
**Latest Released:** 0.7.5 (PyPI, 2026-10-27)

---

## 1. Upstream & Versions

| Item | URL |
|------|-----|
| PyPI Package | https://pypi.org/project/google-colab-cli/ |
| GitHub Repository | https://github.com/googlecolab/google-colab-cli |
| GitHub Issues | https://github.com/googlecolab/google-colab-cli/issues |
| GitHub Releases | https://github.com/googlecolab/google-colab-cli/releases |

### Release History (PyPI)
```
0.5.4 → 0.5.5 → 0.5.6 → 0.5.7 → 0.5.8 → 0.5.9 → 0.5.11 → 0.6.0 → 0.7.2 → 0.7.3 → 0.7.4 → 0.7.5
```
- **Installed:** 0.7.4 (2026-10-21 approx)
- **Latest:** 0.7.5 (2026-10-27)

### 0.7.5 Release Notes (from GitHub Releases API)
> **0.7.5** — Maintenance release; no user-visible changes listed.

### Commits Since 0.7.4 Tag
The `0.7.4...main` compare shows **0 commits** — 0.7.5 appears to be a re-tag or the main branch hasn't diverged from the 0.7.4 tag. The version bump is likely a metadata/build change only.

---

## 2. Changelog 0.7.4 → Latest (0.7.5)

**Effectively no functional changes.** The version bump from 0.7.4 → 0.7.5 contains no listed bugfixes, features, or API changes in the release body. All significant changes relevant to idle/session lifecycle occurred *before* 0.7.4 (see issues below).

### Key Historical Changes (Pre-0.7.4) Relevant to Idle/Session

| Date | PR/Issue | Change |
|------|----------|--------|
| 2026-09-25 | PR #136 | Runtime proxy token refresh before expiry (`token_expires_at` + proactive renewal via `list_assignments`) |
| 2026-09-25 | PR #144 | **Removed client-side keep-alive daemon** — backend now maintains liveness automatically via kernel activity |
| 2026-06-15 | PR #61 | Switched keep-alive from broken gRPC RPC to TFE tunnel ping (`GET /tun/m/<endpoint>/keep-alive/`) |
| 2026-06-10 | PR #60 | Fallback to `list_assignments` when keep-alive RPC fails with auth error |
| 2026-05-07 | — | Fixed `colab console` piped stdin (sends `exit\n` not Ctrl-D) |
| 2026-06-04 | — | Bumped default `--timeout` from 10s → 30s for `colab exec`/`colab run` |
| 2026-10-14 | — | Configurable HTTP timeouts + bounded allocation retries |

---

## 3. Idle/Session-Lifecycle Findings (GitHub Issues)

### What Makes Colab Report a Session as Idle/Nonexistent?

| Cause | Component Responsible | Evidence |
|-------|----------------------|----------|
| **Runtime-proxy token expiry (~1 hour)** | Colab backend (TFE tunnel) | #147: `tokenExpiresInSeconds = 3600`; 401/404 on kernel connect when token stale |
| **VM assignment idle timeout (~7-8 min without activity)** | Colab backend (TFE tunnel) | #61: keep-alive daemon exited after 2 failures → VM idled ~7-8 min later |
| **Server-side runtime GC after idle timeout** | Colab backend | #155: "long-lived sessions keep running but new commands fail due to stale credentials" |
| **Assignment expiry (TooManyAssignmentsError / HTTP 412)** | Colab backend | #147: orphaned assignments accumulate when CLI prunes locally but VM stays alive |
| **WebSocket drop / connection closed** | jupyter-kernel-client / Colab backend | #101: `WebSocketConnectionClosedException` immediately after session creation |

### What Clients Do to Keep Sessions Alive

| Mechanism | Status | Details |
|-----------|--------|---------|
| **Client-side keep-alive daemon (TFE ping every 60s)** | **REMOVED in PR #144 (2026-09-25)** | Was: `GET /tun/m/<endpoint>/keep-alive/` with `X-Colab-Tunnel: Google`; treated `ReadTimeout` as success |
| **Proactive token refresh (5-min margin)** | **ACTIVE (PR #136, in 0.7.4+)** | `State.get_session()` calls `list_assignments()` when `token_expires_at` within 5 min; updates local state |
| **Kernel activity (execution, TTY, WebSocket)** | **ACTIVE (backend-driven)** | PR #144: "runtimes are automatically kept alive by the backend based on kernel activities and active connections" |
| **Reactive recovery on 401/404** | **ACTIVE (PR #136 / #155)** | `is_terminal_error()` detects 401/404; `State.get_session()` refreshes token before pruning; `sync_sessions()` prunes only when endpoint absent from `list_assignments()` |

### Key Issue URLs

| # | Title | State | URL |
|---|-------|-------|-----|
| 144 | refactor: clean up client-side keep-alive | closed | https://github.com/googlecolab/google-colab-cli/pull/144 |
| 147 | Session pruned as 'lost' when runtime-proxy token expires | closed | https://github.com/googlecolab/google-colab-cli/issues/147 |
| 136 | fix: renew the runtime proxy token before it expires | closed | https://github.com/googlecolab/google-colab-cli/pull/136 |
| 155 | Long-lived sessions keep running but new runtime commands fail | closed | https://github.com/googlecolab/google-colab-cli/issues/155 |
| 185 | fix: enforce --timeout as an idle limit without busy-waiting | open | https://github.com/googlecolab/google-colab-cli/pull/185 |
| 101 | WebSocketConnectionClosedException on exec/repl | closed | https://github.com/googlecolab/google-colab-cli/issues/101 |
| 61 | fix(keep-alive): use TFE tunnel ping instead of RuntimeService RPC | closed | https://github.com/googlecolab/google-colab-cli/pull/61 |
| 60 | fix: fall back to list_assignments when KeepAliveAssignment RPC fails | closed | https://github.com/googlecolab/google-colab-cli/pull/60 |

---

## 4. Official Colab Docs

| Topic | Finding | Source |
|-------|---------|--------|
| **Idle timeout** | Not explicitly documented in public FAQ; backend idle-prunes VMs after ~7-8 min without kernel activity or active WebSocket connections | #61, #144, colab-vscode extension behavior |
| **GPU session limits** | Free tier: T4 only; Pro/Pro+: L4, A100, H100; concurrent session limits enforced via HTTP 412 (`TooManyAssignmentsError`) | #191, `colab_cli/client.py:180` |
| **Files when idle** | Files persist in VM filesystem (`/content`) until VM is unassigned; orphaned VMs retain files but become unreachable via CLI | #147: "Results/artifacts on abandoned VMs become unreachable" |
| **Runtime proxy token lifetime** | 3600 seconds (1 hour) — `tokenExpiresInSeconds` field in `RuntimeProxyInfo` | #147, `colab_cli/client.py:123` |
| **SSH session limit** | HTTP 429 when another `colab ssh` connected to same runtime | #191, `colab_cli/commands/ssh.py:270` |

**Note:** The public `colab.research.google.com/faq` and `research.google.com/colaboratory/faq.html` return 403/HTML pages not easily scrapable. The authoritative behavior is encoded in the CLI and colab-vscode extension.

---

## 5. Local Source Analysis (v0.7.4)

### Session State Store
**File:** `colab_cli/state.py`

```python
# Line 25-38: SessionState model
class SessionState(BaseModel):
    name: str
    token: str
    url: str
    endpoint: str
    token_expires_at: Optional[datetime] = None  # ← KEY: expiry tracking
    variant: str = "DEFAULT"
    accelerator: str = "NONE"
    machine_shape: str = "STANDARD"
    kernel_id: Optional[str] = None
    session_id: Optional[str] = None
    last_execution: Optional[Tuple[str, Optional[str], str]] = None
    running: Optional[str] = None
```

### Token Refresh Logic (Proactive)
**File:** `colab_cli/common.py`

```python
# Line 28-29: 5-minute renewal margin
TOKEN_REFRESH_MARGIN = timedelta(minutes=5)

# Line 86-112: get_session() - refreshes token if near expiry
def get_session(self, name: str, ignore_missing_session: bool = False) -> Optional[SessionState]:
    s = self.store.get(name)
    if s and (
        not s.token_expires_at
        or s.token_expires_at - datetime.now(timezone.utc) <= TOKEN_REFRESH_MARGIN
    ):
        by_endpoint = {a.endpoint: a for a in self.client.list_assignments()}
        if s.endpoint in by_endpoint:
            _apply_proxy_info(s, by_endpoint[s.endpoint].runtime_proxy_info)
            self.store.add(s)
        else:
            self.prune_session(name)
            s = None
    ...
```

### Sync & Prune Logic (Reactive Recovery)
**File:** `colab_cli/common.py`

```python
# Line 114-148: sync_sessions() - prunes only when endpoint missing server-side
def sync_sessions(self):
    ...
    assignments = self.client.list_assignments()
    by_endpoint = {a.endpoint: a for a in assignments}
    ...
    for name, s in list(self._sessions.items()):
        if s.endpoint not in by_endpoint:
            self.prune_session(name)  # ← ONLY prunes if assignment gone
            pruned += 1
        else:
            _apply_proxy_info(s, by_endpoint[s.endpoint].runtime_proxy_info)
            self.store.add(s)
```

### TTY / Terminal WebSocket Endpoint
**File:** `colab_cli/console.py`

```python
# Line 133: WebSocket URL construction
ws_url = f"{ws_scheme}://{parsed.netloc}/colab/tty?colab-runtime-proxy-token={session.token}"

# Line 139-145: WebSocketApp setup
ws = websocket.WebSocketApp(
    url=ws_url,
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close,
)
```

**File:** `colab_cli/commands/ssh.py`

```python
# Line 218-225: SSH WebSocket URL
def _build_ws_url(session: SessionState) -> str:
    parsed = urlparse(session.url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/colab/ssh?colab-runtime-proxy-token={session.token}"
```

### Where "Session Does Not Exist" Errors Are Raised
**File:** `colab_cli/utils.py`

```python
# Line 37-46: Terminal error detection (401/404 = lost session)
def is_terminal_error(e: Exception) -> bool:
    code = get_status_code(e)
    if code in (404, 401):
        return True
    err_msg = str(e)
    if "404" in err_msg or "401" in err_msg:
        return True
    return False
```

**File:** `colab_cli/commands/execution.py` (3 sites)

```python
# Line 220-227: exec_command prelude
try:
    runtime.execute_code("import os; os.makedirs('/content', exist_ok=True); os.chdir('/content')")
except Exception as e:
    if is_terminal_error(e):
        typer.echo(f"[colab] Session '{name}' appears to be lost (404/401). Cleaning up.")
        state.prune_session(name)  # ← PRUNES HERE
        raise typer.Exit(1)
    raise e
```

```python
# Line 321-327: repl_command prelude (same pattern)
# Line 387-393: console_command (same pattern)
```

### jupyter_kernel_client Usage

**File:** `colab_cli/runtime.py`

| Method | Line | Purpose |
|--------|------|---------|
| `kernel_client` property | 89-172 | Lazy-initializes `ColabKernelClient` / `KernelClient` / `JupyterKernelClient` with `proxy_token` |
| `execute_code()` | 180-262 | Calls `kernel_client.execute()` or `execute_interactive()` with `output_hook`, `timeout` |
| `restart()` | 174-178 | `kernel_client.restart()` |
| `stop()` | 264-278 | Closes channels + socket; optionally `shutdown_kernel()` |

**File:** `jupyter_kernel_client/client.py` (upstream)

```python
# Line 380-382: is_alive() — delegates to manager
def is_alive(self, timeout: float = REQUEST_TIMEOUT) -> bool:
    return self._manager.is_alive()

# Line 329-335: KernelHttpManager.is_alive() — refreshes model via HTTP
def is_alive(self, timeout: float = REQUEST_TIMEOUT):
    if self.has_kernel:
        self.__kernel = self.refresh_model(timeout)
    return self.has_kernel

# Line 1114-1122: KernelWebSocketClient.is_alive() — uses heartbeat channel
def is_alive(self) -> bool:
    if self._hb_channel is not None:
        return self._hb_channel.is_beating()
    return True  # naive fallback

# Line 1170-1221: wait_for_ready() — waits for kernel_info_reply + heartbeat
```

**File:** `jupyter_kernel_client/wsclient.py`

```python
# Line 486-498: ping_interval=60, reconnect_interval=0 (default)
def __init__(..., ping_interval: float = 60, reconnect_interval: int = 0, ...):
    self.ping_interval: float = ping_interval
    self.reconnect_interval = reconnect_interval
    ...

# Line 1279-1281: WebSocket run_forever with ping
self.kernel_socket.run_forever(
    ping_interval=self.ping_interval, reconnect=self.reconnect_interval
)
```

---

## 6. Direct Answers

### (a) In colab_cli, what part is "in charge of idle"?

**Answer:** **No client-side component is in charge of idle anymore.** Since PR #144 (2026-09-25, released in 0.7.2+), the **client-side keep-alive daemon was completely removed**. The Colab backend now automatically maintains VM liveness based on:
- Active kernel executions (any code running)
- Active WebSocket connections (shell, iopub, stdin, control, heartbeat channels)
- SSH/TTY WebSocket connections

The CLI only handles **token refresh** (proactive, 5-min margin via `State.get_session()`) and **reactive recovery** on 401/404 (via `is_terminal_error()` + `sync_sessions()`).

### (b) Is it the jupyter kernel client?

**Answer:** **Partially.** The `jupyter_kernel_client` maintains the WebSocket connection with:
- **WebSocket ping/pong** every 60s (`ping_interval=60` in `KernelWebSocketClient.__init__`)
- **Heartbeat channel** (`HBWSChannel`) — but it's a stub (`is_beating()` always returns `True`)
- **No application-level keep-alive** — it relies on the Colab backend to keep the VM alive as long as the WebSocket stays open

The `jupyter_kernel_client` does **not** enforce idle timeouts; it only detects connection loss via WebSocket close.

### (c) What must an app do so a session stays alive while the app is open?

**Answer:** Keep **at least one WebSocket channel open** (shell, iopub, stdin, control, or heartbeat) **OR** execute code periodically.

| Approach | Mechanism | Reliability |
|----------|-----------|-------------|
| **Interactive REPL/console/SSH** | Holds WebSocket open continuously | ✅ Best — backend sees active connection |
| **Periodic `execute_code()`** | Any kernel execution resets backend idle timer | ✅ Good — but must be < ~7 min interval |
| **Heartbeat channel** | `KernelWebSocketClient` opens hb channel by default | ⚠️ Stub implementation — `is_beating()` always `True` |
| **Do nothing (idle)** | Backend idle-prunes after ~7-8 min | ❌ Will lose session |

**For ColabShell:** Keep a persistent WebSocket (e.g., the REPL's shell channel) open, or execute a no-op (`pass` or `print()`) every 4-5 minutes.

### (d) Why would the AI assistant say it has no access to an idle session — where in colab_cli is access gated on session state?

**Answer:** Access is gated in **`State.get_session()`** (`colab_cli/common.py:86-112`) and **`sync_sessions()`** (`colab_cli/common.py:114-148`).

The flow:
1. Any command calls `state.resolve_session()` → `state.get_session()`
2. `get_session()` checks `token_expires_at`; if within 5 min or missing, calls `list_assignments()` to fetch fresh token
3. If endpoint **not in** `list_assignments()` response → `prune_session()` → session deleted locally
4. If endpoint **in** response → token refreshed, session preserved
5. On 401/404 from kernel connect (`is_terminal_error()`), `execution.py`/`repl.py`/`console.py` call `prune_session()` **before** retrying

**The gate:** `State.get_session()` returns `None` (or raises `typer.Exit`) when:
- No local session exists, OR
- Token expired and `list_assignments()` shows no matching endpoint (VM truly gone), OR
- 401/404 on kernel connect triggers immediate prune (race: token expired but VM still alive)

---

## 7. Recommendations for ColabShell (Keep-Alive Design)

### What to Ping
| Target | Endpoint | Frequency | Why |
|--------|----------|-----------|-----|
| **Kernel WebSocket (shell channel)** | Implicit via `jupyter_kernel_client` | 60s (built-in ping) | Keeps TCP connection alive; backend tracks active channels |
| **Explicit no-op execution** | `runtime.execute_code("pass")` | Every 4-5 min | Resets backend idle timer definitively; works even if WebSocket ping is insufficient |
| **TTY/SSH WebSocket** | `/colab/tty` or `/colab/ssh` | Continuous | If using console/SSH mode, this alone keeps VM alive |

### Recommended Keep-Alive Strategy for ColabShell

```python
# In ColabShell's session manager:
class ColabShellSession:
    def __init__(self, runtime: ColabRuntime):
        self.runtime = runtime
        self._keepalive_task = None
        self._keepalive_interval = 300  # 5 minutes
    
    async def start_keepalive(self):
        """Start background task to keep session alive."""
        async def keepalive_loop():
            while True:
                await asyncio.sleep(self._keepalive_interval)
                try:
                    # Option 1: Execute no-op (most reliable)
                    self.runtime.execute_code("pass", timeout=10)
                except Exception as e:
                    if is_terminal_error(e):
                        # Session truly lost — trigger reconnect
                        await self.handle_session_lost()
                    # else: transient error, retry next cycle
        
        self._keepalive_task = asyncio.create_task(keepalive_loop())
    
    async def stop_keepalive(self):
        if self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
```

### TTY Ping vs Execute
| Method | Pros | Cons |
|--------|------|------|
| **WebSocket ping (built-in)** | Zero overhead; automatic | May not reset Colab's idle timer (backend tracks kernel activity, not TCP) |
| **`execute_code("pass")`** | Definitively resets idle timer; verifies kernel responsive | Consumes execution quota; slight latency |
| **TTY/SSH WebSocket** | Keeps VM alive as long as connected | Only works in console/SSH mode |

**Recommendation:** Use **periodic `execute_code("pass")`** as primary keep-alive (every 4-5 min). The WebSocket ping is a supplement.

### Reconnect Logic
When `is_terminal_error()` (401/404) or WebSocket close detected:

```python
async def handle_session_lost(self):
    # 1. Try token refresh first (proactive path)
    try:
        fresh_session = state.get_session(self.session_name, ignore_missing_session=True)
        if fresh_session and fresh_session.endpoint in current_assignments:
            self.runtime = ColabRuntime(fresh_session.url, fresh_session.token, ...)
            return  # Recovered!
    except Exception:
        pass
    
    # 2. Sync with server — maybe assignment still exists
    sessions, assignments = state.sync_sessions()
    if self.session_name in sessions:
        s = sessions[self.session_name]
        self.runtime = ColabRuntime(s.url, s.token, ...)
        return
    
    # 3. Truly gone — notify user, offer to create new
    raise SessionLostError("Session expired on backend; run 'colab new'")
```

### Key Parameters
| Parameter | Value | Source |
|-----------|-------|--------|
| Backend idle timeout | ~7-8 minutes | #61, colab-vscode |
| Runtime proxy token TTL | 3600s (1 hour) | #147, `client.py:123` |
| Token refresh margin | 300s (5 min) | `common.py:29` |
| WebSocket ping interval | 60s | `wsclient.py:496` |
| Recommended keep-alive interval | 240-300s (4-5 min) | Safety margin under 7-8 min |

---

## Summary

- **0.7.4 → 0.7.5**: No functional changes
- **Idle management**: Fully backend-driven since PR #144 (Sept 2025); client only does token refresh
- **Session loss causes**: Token expiry (1h), backend idle timeout (~7-8 min), assignment expiry (412)
- **Keep-alive for ColabShell**: Execute `pass` every 4-5 min via `runtime.execute_code()`; supplement with WebSocket ping
- **Access gate**: `State.get_session()` + `is_terminal_error()` in execution commands
