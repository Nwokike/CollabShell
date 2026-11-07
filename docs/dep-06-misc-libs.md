# Misc Libraries Audit — ColabShell (since v2.1.2)

**Repo:** `/home/maikel/Desktop/kiri-apps/ColabShell` (branch `main`, HEAD `76a9d4b`)  
**Source of truth:** `/home/maikel/Desktop/kiri-apps/ColabShell/.venv/lib/python3.14/site-packages/`  
**Scope:** Third-party packages imported in `src/` and `scripts/` that are **not** covered in:
- `dep-01-flet-core.md` (flet, flet_ads, flet_terminal)
- `dep-03-colab-libs.md` (colab_cli, google_auth_oauthlib, oauthlib, requests via colab_cli)
- `dep-04-ai-libs.md` (kani, openai, httpx, tiktoken)
- `audit-03-ads-premium-license.md` (cryptography NOT used — pure-Python ECDSA in license_token.py)

**Packages found in app imports:**

| Package | Import Location | Version (site-packages) |
|---------|----------------|------------------------|
| `requests` | `src/services/colab/terminal_client.py:21` | 2.34.2 |
| `tornado.websocket` | `src/services/colab/terminal_client.py:23` | 6.5.10 |
| `tornado.httpclient` | `src/services/colab/terminal_client.py:22` | 6.5.10 |
| `rich.ansi` | `src/components/ansi_parser.py:2` | 15.0.0 |

**Packages in venv but NOT imported in app:**
- `qrcode` (8.2) — no import found
- `PIL`/`pillow` (13.0.0) — no import found
- `arrow` (1.4.0) — no import found
- `dateutil` (2.9.0) — no import found
- `oauthlib` (4.0.0) — used transitively via `google_auth_oauthlib` in colab_cli
- `requests_oauthlib` (2.0.0) — used transitively via `google_auth_oauthlib`
- `google_auth` (2.61.0) — used transitively via `google_auth_oauthlib`
- `google_auth_oauthlib` (1.5.0) — imported in `colab_cli`, not directly in app
- `websocket_client` (1.9.2) — not used; app uses `tornado.websocket`
- `msgpack` (1.2.3) — no import found
- `html2text` (2025.4.15) — no import found
- `markdown_it` (4.2.0) — no import found
- `pygments` (2.21.0) — no import found
- `anyio` (4.15.1) — only a comment reference in `router_engine.py`
- `typer` (0.27.3) / `click` (8.5.0) — not used directly; mentioned in `main.py:22` comment about colab_cli
- `yaml` (6.0.3) — no import found
- `jinja2` (3.1.6) — no import found
- `fastjsonschema` (2.22.2) / `jsonschema` (4.26.0) — no import found
- `annotated_doc` (0.0.5) — no import found

---

## 1. `requests` (v2.34.2)

### What the App Does
**File:** `src/services/colab/terminal_client.py`  
**Lines:** 33-65 (`create_terminal_ws_url`)

```python
# Line 51-57
resp = requests.post(post_url, headers=headers, timeout=10)
resp.raise_for_status()
term_info = resp.json()
term_name = term_info["name"]
```

Creates a Colab PTY terminal via `POST /api/terminals` with the runtime-proxy token. Uses `requests` synchronously inside a `asyncio.to_thread` call (see `terminal_client.py:291-296`).

### What the Library Really Offers
**Source:** `.venv/lib/python3.14/site-packages/requests/__init__.py` + `api.py`

```python
# requests/api.py:61-68
def post(url, data=None, json=None, **kwargs):
    return request("post", url, data=data, json=json, **kwargs)

# requests/models.py:980-1010 (Response.raise_for_status)
def raise_for_status(self):
    if 400 <= self.status_code < 500:
        raise HTTPError(...)
    elif 500 <= self.status_code < 600:
        raise HTTPError(...)
```

Key behaviors:
- `timeout=10` applies to **both connect and read** (single float = total timeout)
- No automatic retry; `raise_for_status()` raises `HTTPError` on 4xx/5xx
- `Response.json()` parses JSON or raises `JSONDecodeError`
- Session objects (`requests.Session`) provide connection pooling, cookie persistence, and adapter configuration — **not used**

### Gap Analysis

| # | Severity | App Location | Library Source | Problem | Better Way |
|---|----------|--------------|----------------|---------|------------|
| 1 | **medium** | `terminal_client.py:51` | `requests/api.py:61` | **Sync `requests.post` in async context** — wrapped in `asyncio.to_thread` (line 291-296), but blocks a thread. The app already uses `httpx` elsewhere (router_engine, license_service). | Use `httpx.AsyncClient.post` with same timeout semantics. Share client with other services for connection pooling. |
| 2 | **medium** | `terminal_client.py:51` | `requests/models.py:980` | **Single timeout value** — `timeout=10` means total (connect+read). No separate connect/read control. Colab's `/api/terminals` may hang on connect. | Use `httpx.Timeout(connect=5.0, read=10.0)` for explicit control. |
| 3 | **low** | `terminal_client.py:291-296` | `requests/sessions.py` | **No connection pooling** — new TCP connection per `requests.post`. The app creates PTY once per session, so low impact, but inconsistent with `httpx` usage elsewhere. | Use shared `httpx.AsyncClient` with `limits=httpx.Limits(max_keepalive_connections=5)`. |
| 4 | **info** | `terminal_client.py:57` | `requests/models.py:900` | **`resp.json()` without error handling** — if Colab returns non-JSON (e.g., HTML error page), raises `JSONDecodeError` uncaught. | Check `resp.headers.get("content-type")` or wrap in try/except. |

---

## 2. `tornado` (v6.5.10) — WebSocket Client

### What the App Does
**File:** `src/services/colab/terminal_client.py`  
**Lines:** 68-402 (`ColabTerminalClient` class)

Key usage:
```python
# Line 157-161: Connection
req = tornado.httpclient.HTTPRequest(self.ws_url, connect_timeout=15)
self.ws = await websocket_connect(req)

# Line 189-191: Read with timeout
msg = await asyncio.wait_for(my_ws.read_message(), timeout=WS_PING_INTERVAL)

# Line 249: Ping
self.ws.ping(PING_PAYLOAD)

# Line 367-368: Write
msg = json.dumps(["stdin", payload])
await self.ws.write_message(msg)

# Line 380: Resize
msg = json.dumps(["set_size", rows, cols])
await self.ws.write_message(msg)
```

Implements a **PTY WebSocket client** for Colab terminals (`/terminals/websocket/{name}`), with:
- Reconnection logic (exponential backoff, max 12 attempts)
- Ping/pong keepalive (10s interval)
- Credential refresh on reconnect (re-reads runtime-proxy token)
- Message parsing for stdout, setup, disconnect

### What the Library Really Offers
**Source:** `.venv/lib/python3.14/site-packages/tornado/websocket.py`

```python
# Line 1632-1725: websocket_connect
def websocket_connect(
    url,
    callback=None,
    connect_timeout=None,
    on_message_callback=None,
    compression_options=None,
    ping_interval=None,      # <-- built-in ping
    ping_timeout=None,       # <-- built-in pong timeout
    max_message_size=10MB,
    subprotocols=None,
    resolver=None,
) -> Awaitable[WebSocketClientConnection]:
```

```python
# Line 1388-1620: WebSocketClientConnection
class WebSocketClientConnection:
    def __init__(self, request, on_message_callback=None, compression_options=None,
                 ping_interval=None, ping_timeout=None, max_message_size=10MB, ...):
    
    async def read_message(self) -> Union[None, str, bytes]: ...
    def write_message(self, message, binary=False) -> Future: ...
    def ping(self, data=b"") -> None: ...
    def close(self, code=None, reason=None) -> None: ...
    @property
    def selected_subprotocol(self) -> Optional[str]: ...
```

**Built-in features the app reimplements:**
| Feature | App Implementation | Tornado Built-in |
|---------|-------------------|------------------|
| Ping interval | `WS_PING_INTERVAL=10`, manual `ping()` in `_probe_upstream` | `ping_interval` param in `websocket_connect` / `WebSocketClientConnection` |
| Pong timeout | Not implemented | `ping_timeout` param — auto-closes if pong not received |
| Max message size | Not enforced | `max_message_size=10*1024*1024` default |
| Compression | Not used | `compression_options` (permessage-deflate) |
| Subprotocols | Not used | `subprotocols` param |
| Auto-reconnect | Custom `_reconnect_with_backoff` (12 attempts, 1s→15s) | **None** — must implement manually |

### Gap Analysis

| # | Severity | App Location | Library Source | Problem | Better Way |
|---|----------|--------------|----------------|---------|------------|
| 1 | **high** | `terminal_client.py:189-191` | `websocket.py:1553-1571` | **Manual read timeout + ping** — `asyncio.wait_for(ws.read_message(), timeout=10)` + custom `ping()`. Tornado supports `ping_interval` + `ping_timeout` natively, which handles keepalive at protocol level without app-level timeout logic. | Use `websocket_connect(..., ping_interval=10, ping_timeout=5)` and remove manual ping/timeout logic. |
| 2 | **high** | `terminal_client.py:244-252` | `websocket.py:1585-1602` | **`_probe_upstream` sends ping but ignores pong** — `ws.ping()` returns immediately; no verification that pong received. If network partitioned, ping succeeds locally but pong never arrives. | Use `ping_timeout` in `websocket_connect` — Tornado closes connection automatically on pong timeout. |
| 3 | **medium** | `terminal_client.py:157-161` | `websocket.py:1695-1725` | **`connect_timeout=15` only** — no read timeout on initial handshake. If Colab accepts TCP but stalls on WS upgrade, hangs 15s. | Add `request.connect_timeout=15` AND `request.request_timeout=30` (total). Or use `websocket_connect(connect_timeout=15)` which applies to handshake. |
| 4 | **medium** | `terminal_client.py:277-328` | `websocket.py:1388-1620` | **Custom reconnection logic** — 12 attempts, exponential backoff. No standard retry policy in Tornado, but app logic doesn't respect `WebSocketClosedError` codes (1000=normal, 1006=abnormal). | Classify close codes: 1000/1001=don't retry; 1006/1011=retry. Current code retries on all drops. |
| 5 | **low** | `terminal_client.py:367-368` | `websocket.py:1537-1551` | **`write_message` returns `Future` not awaited** — fire-and-forget. If send buffer full, backpressure ignored. | `await self.ws.write_message(msg)` or handle returned `Future` for flow control. |
| 6 | **low** | `terminal_client.py:212-230` | `websocket.py:106-117` | **Message parsing assumes JSON list/dict** — Colab protocol uses `["stdout", "text"]` and `{"data": "..."}`. No schema validation; malformed messages logged but not rejected. | Define `TypedDict` for message types; validate before processing. |
| 7 | **info** | `terminal_client.py:33-65` | `colab_cli/console.py:123-133` | **Different endpoint than library** — app uses PTY (`/terminals/websocket` + POST `/api/terminals`); `colab_cli` uses raw TTY (`/colab/tty`). PTY supports resize, persistent shell; TTY is simpler. | Document difference. App's PTY approach is superior for interactive use. |

---

## 3. `rich` (v15.0.0) — ANSI Parsing

### What the App Does
**File:** `src/components/ansi_parser.py`  
**Lines:** 1-190 (`parse_ansi_to_flet_text`)

```python
# Line 96-97
decoder = AnsiDecoder()
decoded_lines = list(decoder.decode(cleaned_text))

# Line 111-170: Iterate spans, convert to Flet TextSpans
for span in spans:
    flet_color = _rich_color_to_hex(span.style.color) or default_color
    weight = ft.FontWeight.BOLD if span.style.bold else None
    italic = span.style.italic
    bgcolor = _rich_color_to_hex(span.style.bgcolor)
    # ... build ft.TextSpan ...
```

Parses terminal ANSI output (from Colab) into Flet `Text` with `TextSpan` styling. Handles:
- SGR codes (bold, italic, underline, strikethrough)
- 16-color, 256-color, truecolor (RGB)
- Background colors
- Carriage return cleaning (simulates terminal overwrite)

### What the Library Really Offers
**Source:** `.venv/lib/python3.14/site-packages/rich/ansi.py`

```python
# Line 120-211: AnsiDecoder
class AnsiDecoder:
    def __init__(self): self.style = Style.null()
    def decode(self, terminal_text: str) -> Iterable[Text]: ...
    def decode_line(self, line: str) -> Text: ...
```

```python
# Line 59-117: SGR_STYLE_MAP (partial)
SGR_STYLE_MAP = {
    1: "bold", 3: "italic", 4: "underline", 9: "strike",
    22: "not dim not bold", 23: "not italic", 24: "not underline",
    30-37: "color(0-7)", 39: "default",
    40-47: "on color(0-7)", 49: "on default",
    90-97: "color(8-15)", 100-107: "on color(8-15)",
}
```

**Key behaviors:**
- `decode()` yields `Text` objects per line (splits on `\n`)
- `Text.spans` contains `(start, end, Style)` tuples
- `Style` has: `color`, `bgcolor`, `bold`, `italic`, `underline`, `strike`, `overline`, `link`, etc.
- `Color` has: `triplet` (RGB), `number` (ANSI index), `type` (standard/256/truecolor)
- **Stateful decoder** — `self.style` accumulates across lines (intended for streaming)

### Gap Analysis

| # | Severity | App Location | Library Source | Problem | Better Way |
|---|----------|--------------|----------------|---------|------------|
| 1 | **medium** | `ansi_parser.py:96` | `ansi.py:123-124` | **New `AnsiDecoder()` per call** — correct for isolation, but `AnsiDecoder` is stateful across lines *within* one `decode()` call. App splits by `\n` then calls `decoder.decode(cleaned_text)` once — this works because `decode()` processes all lines in one go, maintaining style state across lines. | Current usage is correct. However, if app ever streams chunks, must reuse decoder instance. |
| 2 | **medium** | `ansi_parser.py:102-109` | `ansi.py:135-136` | **`_MAX_SPANS = 2000` hard limit** — truncates styled output silently. A malicious or buggy terminal could generate >2000 spans (e.g., rapid color changes). Fallback to plain text loses all formatting. | Consider `MAX_SPANS` as config; log warning when hit; preserve last N spans instead of first N. |
| 3 | **low** | `ansi_parser.py:74-84` | `ansi.py:28-56` | **Carriage return handling** — splits on `\r`, takes last non-empty segment per line. This simulates terminal overwrite but **breaks multi-line ANSI sequences** that span across `\r` boundaries (rare but possible). | Use `AnsiDecoder` streaming: feed chunks as they arrive, let it handle `\r` internally. |
| 4 | **low** | `ansi_parser.py:140-157` | `ansi.py:177-209` | **Decoration mapping** — combines underline + strikethrough via `TextDecoration.combine()`. Flet's `TextDecoration` enum may not support all combinations. | Test combined decorations; fallback to single decoration if combine fails. |
| 5 | **info** | `ansi_parser.py:11-58` | `ansi.py:59-117` | **Custom color map for 16 colors** — duplicates `rich.color.Color.from_ansi` logic. Rich's `Color.from_ansi(n)` returns standard 16-color RGB values. | Use `Color.from_ansi(n).triplet` for 0-15 instead of hardcoded `cmap`. |
| 6 | **info** | `ansi_parser.py:45-56` | `ansi.py:46-56` | **256-color cube math** — reimplements 6×6×6 color cube (colors 16-231) and grayscale ramp (232-255). Matches Rich's internal logic. | Could use `Color.from_ansi(n)` for all ANSI colors if Rich exposes it (it does via `Color.from_ansi`). |

**Rich features NOT used but available:**
| Feature | Source | Potential Use |
|---------|--------|---------------|
| `AnsiDecoder.decode()` streaming | `ansi.py:126-136` | Feed terminal output chunk-by-chunk instead of full string |
| `Style.link` / `Style.meta` | `style.py` | Hyperlink detection in terminal output (OSC 8) |
| `Text.highlight_regex()` | `text.py` | Search/highlight in terminal buffer |
| `Console.render_lines()` | `console.py` | Full terminal emulation (cursor movement, scroll regions) — app only handles SGR |

---

## 4. `flet_terminal` (v0.3.9) — Terminal Widget

### What the App Does
**File:** `src/screens/session/terminal_panel.py`  
**Lines:** 1-500+

```python
# Line 12: Import
from flet_terminal import BUILTIN_THEMES, MobileTerminal

# Line 338-353: In _TerminalHost component
terminal = MobileTerminal(
    on_data=lambda e: _on_stdout(e.data),
    on_binary=lambda e: _on_binary(e.data),
    on_resize=lambda e: _on_resize(e.cols, e.rows),
    theme=theme,
    font_size=state.terminal_font_size,
    cursor_blink=state.terminal_cursor_blink,
    cursor_style=state.terminal_cursor_style,
    scrollback=state.terminal_scrollback,
    quick_commands=state.terminal_quick_commands,
)
```

Uses `MobileTerminal` (Dart-backed GPU terminal) for Colab PTY sessions. Handles:
- Stdout via `on_data` callback
- Binary data via `on_binary`
- Resize notifications
- Theme switching (built-in themes)
- Font size, cursor style, scrollback config

### What the Library Really Offers
**Source:** `.venv/lib/python3.14/site-packages/flet_terminal/`

```python
# mobile_terminal.py: MobileTerminal class (Flet control)
class MobileTerminal(ft.Control):
    def __init__(
        self,
        on_data: Callable = None,
        on_binary: Callable = None,
        on_resize: Callable = None,
        theme: str = "default",
        font_size: int = 14,
        cursor_blink: bool = True,
        cursor_style: str = "block",  # "block" | "underline" | "bar"
        scrollback: int = 10000,
        quick_commands: List[str] = None,
    ):
```

```python
# themes.py: BUILTIN_THEMES
BUILTIN_THEMES = {
    "default": TerminalTheme(...),
    "dracula": TerminalTheme(...),
    "github-dark": TerminalTheme(...),
    "monokai": TerminalTheme(...),
    "solarized-dark": TerminalTheme(...),
    "solarized-light": TerminalTheme(...),
}
```

```python
# terminal.py: Terminal class (base)
class Terminal(ft.Control):
    def send(self, data: str): ...          # Send text to terminal
    def send_bytes(self, data: bytes): ...  # Send binary
    def resize(self, cols: int, rows: int): ...
    def clear(self): ...
    def reset(self): ...
```

**Key behaviors:**
- Dart-side PTY handling (xterm.js + Flutter)
- `send()` / `send_bytes()` for stdin
- `resize()` for dimension changes
- Themes are `TerminalTheme` objects (background, foreground, cursor, ANSI palette)
- `quick_commands` shows toolbar with predefined commands

### Gap Analysis

| # | Severity | App Location | Library Source | Problem | Better Way |
|---|----------|--------------|----------------|---------|------------|
| 1 | **medium** | `terminal_panel.py:359` | `mobile_terminal.py` | **`send_bytes` not used for stdin** — app uses `send(data)` (text). Colab PTY expects UTF-8 text; binary mode not needed. But `send_bytes` exists for raw byte streams. | Current usage correct for text PTY. Document why `send_bytes` not used. |
| 2 | **medium** | `terminal_panel.py:360` | `mobile_terminal.py` | **`on_binary` handler unused** — Colab PTY sends ANSI text, not binary. Handler exists but never triggered. | Remove or document as future-proofing. |
| 3 | **low** | `terminal_panel.py:340` | `themes.py:15-25` | **Theme hardcoded to `BUILTIN_THEMES` keys** — app cycles through themes by name string. No validation that theme exists. | Validate theme name against `BUILTIN_THEMES.keys()`; fallback to "default". |
| 4 | **low** | `terminal_panel.py:341-346` | `mobile_terminal.py` | **Font size / cursor / scrollback from state** — reactive but no bounds checking. Dart may crash on extreme values (e.g., `font_size=1`). | Clamp values: `font_size=max(6, min(72, ...))`, `scrollback=max(100, min(100000, ...))`. |
| 5 | **info** | `terminal_panel.py` | `extra_keys.py` | **`ExtraKeysBar` not used** — library provides on-screen key toolbar (Esc, Tab, Ctrl, arrows). App uses Flet keyboard shortcuts instead. | Could add `ExtraKeysBar` for mobile UX where hardware keyboard absent. |
| 6 | **info** | `terminal_panel.py` | `search_bar.py` | **`TerminalSearchBar` not used** — library provides find-in-terminal UI. | Could integrate for log/search in terminal output. |

---

## 5. Cryptography Note

**The app does NOT use the `cryptography` package directly.**

License token verification (`src/services/license_token.py`) implements **pure-Python ECDSA P-256** verification:
- Lines 28-34: P-256 domain parameters (hardcoded)
- Lines 89-175: Point addition, scalar multiplication, ECDSA verify
- Lines 115-136: Strict SPKI parsing (91 bytes, correct prefix)
- Lines 178-187: Signature verification (raw r||s, 64 bytes)

This is a **verbatim port** from ktv-player. The `cryptography` package in venv is a transitive dependency (likely from `google-auth` or `oauthlib`).

**Security audit of pure-Python implementation** (from `audit-03-ads-premium-license.md` finding #6, #14):
| # | Severity | Location | Finding |
|---|----------|----------|---------|
| 6 | **medium** | `license_token.py:190-217` | Adds scope validation (`_check_scope`), payload size limits, clock skew tolerance, `nbf` claim, `paid_through` type check — not in DDGS reference. Breaks compatibility if Worker changes token structure. |
| 14 | **info** | `license_token.py` | Enhanced verification (strict SPKI length/prefix, scope check, size limits, clock skew, `nbf`, `paid_through` type) — more secure than DDGS but diverges from reference. |

**Verdict:** Pure-Python crypto is correct for P-256 ECDSA verify-only. No private key operations. Side-channel resistance not required (verification only). The enhancements are defensive but create Worker compatibility risk.

---

## Summary: Critical/High Priority Gaps

| # | Package | Fix | Files |
|---|---------|-----|-------|
| 1 | `tornado` | Use built-in `ping_interval`/`ping_timeout` instead of manual ping/timeout logic | `terminal_client.py:157-161, 189-191, 244-252` |
| 2 | `tornado` | Classify WebSocket close codes for reconnection (don't retry 1000/1001) | `terminal_client.py:277-328` |
| 3 | `requests` | Replace sync `requests.post` with `httpx.AsyncClient.post` for consistency | `terminal_client.py:51, 291-296` |
| 4 | `rich` | Use `Color.from_ansi()` instead of custom color maps | `ansi_parser.py:11-58` |
| 5 | `rich` | Make `_MAX_SPANS` configurable; log warning when hit | `ansi_parser.py:8, 102-109` |

---

## Library Options Not Exposed by App

| Package | Feature | Source | Why Expose |
|---------|---------|--------|------------|
| `tornado` | `compression_options` (permessage-deflate) | `websocket.py:1434-1442` | Reduce bandwidth for terminal traffic |
| `tornado` | `subprotocols` | `websocket.py:1432-1433` | Negotiate Colab-specific subprotocol if added |
| `tornado` | `max_message_size` | `websocket.py:1404, 1417` | Protect against oversized frames (currently 10MB default) |
| `requests` / `httpx` | Connection pooling / keepalive | `requests/sessions.py`, `httpx/_client.py` | Reuse connections for PTY creation + other Colab API calls |
| `rich` | Streaming `AnsiDecoder` | `ansi.py:126-136` | Parse terminal output incrementally (lower memory) |
| `rich` | OSC 8 hyperlink detection | `ansi.py:157-160` | Clickable links in terminal output |
| `flet_terminal` | `ExtraKeysBar` | `extra_keys.py` | On-screen keys for mobile terminal |
| `flet_terminal` | `TerminalSearchBar` | `search_bar.py` | Find in terminal buffer |
| `flet_terminal` | `TerminalTheme` custom | `themes.py` | User-defined terminal color schemes |

---

## Files Audited (Complete)

| File | Packages Used |
|------|--------------|
| `src/services/colab/terminal_client.py` | `requests`, `tornado.httpclient`, `tornado.websocket` |
| `src/components/ansi_parser.py` | `rich.ansi` |
| `src/screens/session/terminal_panel.py` | `flet_terminal` |

*Generated by audit of `.venv/lib/python3.14/site-packages/` and app source at HEAD `76a9d4b`.*