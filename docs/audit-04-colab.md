# Colab Remote-Session Code Audit: v2.1.2 → HEAD

**Scope**: All Colab remote-session code in `src/services/colab/` and `src/screens/session/`  
**Baseline**: tag `v2.1.2` vs HEAD (`76a9d4b`, squashed commit of all changes since v2.1.2)  
**Source of truth**: Installed `colab_cli` package at `/home/maikel/Desktop/kiri-apps/ColabShell/.venv/lib/python3.14/site-packages/colab_cli/` (version 0.7.4)

---

## Summary Table

| # | Severity | Location | Finding |
|---|----------|----------|---------|
| 1 | **critical** | `src/services/colab/terminal_client.py:33-65` | Terminal uses **wrong WebSocket endpoint** (`/terminals/websocket/` vs library's `/colab/tty/`) — incompatible with upstream |
| 2 | **critical** | `src/services/colab/session_ops.py:69-207` | `keep_alive` parameter **removed** without replacement; upstream has no built-in keep-alive, app's in-process loop was fragile |
| 3 | **high** | `src/services/colab/auth.py:29-107` | **ADC auth provider not exposed** to users; library supports both OAUTH2 and ADC |
| 4 | **high** | `src/services/colab/execution.py:69-70` | Default timeout changed from **60s → 30s** without migration path; upstream `jupyter_kernel_client` defaults to 10s |
| 5 | **high** | `src/services/colab/files_ops.py:198-289` | **Folder download as zip** reimplemented by running `zip` on VM; upstream has no such API — custom, fragile |
| 6 | **medium** | `src/services/colab/auth.py:75-158` | Token refresh logic **duplicated** from upstream instead of using library's built-in `Credentials.refresh()` |
| 7 | **medium** | `src/services/colab/session_ops.py:69-207` | High-RAM shape **only exposed via `high_mem` flag**; library's `Shape` enum (STANDARD/HIGH_RAM) not fully surfaced |
| 8 | **medium** | `src/services/colab/vm_ops.py:8-35` | `mount_drive` hardcodes `drive.mount()` path; library has no Drive mount API — app reimplements via `exec_code` |
| 9 | **medium** | `src/services/colab/usage_ops.py:42-58` | Usage fetch **swallows all exceptions** and returns `None`; no distinction between auth/offline/rate-limit |
| 10 | **low** | `src/services/colab/execution.py:399-410` | History logs **env keys only, not values** — deliberate divergence from upstream which logs prelude verbatim |
| 11 | **low** | `src/services/colab/files_ops.py:53-72` | Upload uses **base64 encoding** (correct per upstream) but no progress callback for large files |
| 12 | **info** | `src/components/hardware_picker.py:105-130` | Hardware picker **correctly mirrors** library's `Accelerator` enum and `HIGH_MEM_ONLY_ACCELERATORS` logic |
| 13 | **info** | `src/services/colab/execution.py:20-66` | Output mapper `_to_cell_output` **preserves mime bundles** (images, execution_count) — fixes v2.1.2 flattening bug |

---

## Detailed Findings

---

### 1. Terminal WebSocket Endpoint Mismatch (Critical)

**Location**: `src/services/colab/terminal_client.py:33-65`  
**Changed since 2.1.2**: Yes (rewritten to use tornado + Jupyter terminal protocol)

**Problem**: The app implements its own terminal WebSocket client against `/terminals/websocket/{name}?colab-runtime-proxy-token={token}`, but the upstream `colab_cli` library uses a completely different endpoint: `/colab/tty?colab-runtime-proxy-token={token}` (see `.venv/lib/python3.14/site-packages/colab_cli/console.py:131-133`).

**Evidence — App code** (`terminal_client.py:33-65`):
```python
def create_terminal_ws_url(raw_url: str, token: str, term_name: str | None = None) -> str:
    ...
    if term_name is None:
        post_url = f"{base_url}/api/terminals?colab-runtime-proxy-token={token}"
        ...
        resp = requests.post(post_url, headers=headers, timeout=10)
        term_name = resp.json()["name"]
    ...
    ws_url = (
        f"{ws_scheme}://{parsed.netloc}/terminals/websocket/{term_name}"
        f"?colab-runtime-proxy-token={token}"
    )
```

**Evidence — Library source** (`.venv/lib/python3.14/site-packages/colab_cli/console.py:131-133`):
```python
parsed = urlparse(session.url)
ws_scheme = "wss" if parsed.scheme == "https" else "ws"
ws_url = f"{ws_scheme}://{parsed.netloc}/colab/tty?colab-runtime-proxy-token={session.token}"
```

**Better way**: Use the library's `connect_console()` function (`.venv/lib/python3.14/site-packages/colab_cli/console.py:123-172`) which handles the correct endpoint, TTY raw mode, SIGWINCH resize handling, and piped-input EOF gracefully. The app's custom implementation reimplements all this incorrectly against the wrong endpoint.

**Library options to expose**: None needed — just call `colab_cli.console.connect_console(session_state)`.

---

### 2. Keep-Alive Parameter Removed Without Replacement (Critical)

**Location**: `src/services/colab/session_ops.py:69-207`  
**Changed since 2.1.2**: Yes (v2.1.2 had `keep_alive: bool = True`; HEAD has `high_mem: bool = False`)

**Problem**: v2.1.2 implemented an in-process keep-alive loop that pinged the assignment endpoint every 60s. This was removed in HEAD. The upstream library **has no built-in keep-alive mechanism** — the `Client` class only has `assign()`, `unassign()`, `list_assignments()`, `get_consumption_user_info()`. The app's keep-alive was a custom workaround for proxy token expiration.

**Evidence — v2.1.2** (session_ops.py:69-130):
```python
async def new_session_impl(..., keep_alive: bool = True) -> dict:
    ...
    if keep_alive:
        try:
            st.client.keep_alive_assignment(endpoint)  # <-- PRE-FLIGHT CHECK
        ...
        st.store.add(s)
        s.keep_alive_pid = None
    ...
    if keep_alive:
        service._start_in_process_keep_alive(...)
```

**Evidence — HEAD** (session_ops.py:69-207): No keep-alive logic at all. Token refresh now happens on-demand via `load_session_fresh()` and `_refresh_runtime_token_sync()`.

**Better way**: The current on-demand token refresh (`load_session_fresh` → `_refresh_runtime_token_sync`) is the correct approach per upstream patterns. However, the **removal should be documented** as a breaking change: long-running sessions that relied on the keep-alive loop will now experience 404s on first operation after token expiry, triggering a one-time heal. This is acceptable but should be in release notes.

---

### 3. ADC Auth Provider Not Exposed (High)

**Location**: `src/services/colab/auth.py:29-107`  
**Changed since 2.1.2**: No (v2.1.2 also only used OAUTH2)

**Problem**: The upstream library defines `AuthProvider` enum with two values: `OAUTH2` and `ADC` (Application Default Credentials). The app only implements OAUTH2 flow. ADC is the standard GCP auth path (`gcloud auth application-default login`) and works on GCE/GKE, Cloud Run, etc.

**Evidence — Library source** (`.venv/lib/python3.14/site-packages/colab_cli/auth.py:33-41, 222-242`):
```python
class AuthProvider(str, enum.Enum):
    OAUTH2 = "oauth2"
    ADC = "adc"

def get_credentials(
    config_path: Optional[str] = None,
    provider: AuthProvider = AuthProvider.OAUTH2,
) -> requests.AuthorizedSession:
    if provider == AuthProvider.OAUTH2:
        ...
    elif provider == AuthProvider.ADC:
        creds = _get_adc_credentials()  # Uses google.auth.default(scopes=PUBLIC_SCOPES)
    ...
```

**Evidence — App code** (`auth.py:75-107`): Only implements `get_auth_url_impl` and `authenticate_oauth2_impl` for the remote OAuth2 flow. No ADC path.

**Better way**: Add an `auth_method` parameter (already present in session_ops/execution/files_ops as `"oauth2" | "adc"`) to the auth service. Expose `ADC` in the UI with a "Use Application Default Credentials" option that skips the OAuth flow and uses `google.auth.default()`.

**Library options to expose**: `AuthProvider.ADC` — requires user to have run `gcloud auth application-default login --scopes=openid,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/colaboratory`.

---

### 4. Default Execution Timeout Changed 60s → 30s (High)

**Location**: `src/services/colab/execution.py:69-70`  
**Changed since 2.1.2**: Yes (v2.1.2: `timeout: float = 60.0`; HEAD: `timeout: float = 30.0`)

**Problem**: The default timeout for code execution was halved without a migration path or config option. The upstream `jupyter_kernel_client` defaults to 10s wall-clock (see `.venv/lib/python3.14/site-packages/colab_cli/runtime.py:188-197`), but the CLI `colab exec` command uses 30s (`.venv/lib/python3.14/site-packages/colab_cli/commands/execution.py:150-153`). The app now matches the CLI default but diverges from its own v2.1.2 behavior.

**Evidence — App code** (`execution.py:69-70`):
```python
async def exec_code_impl(
    ...,
    timeout: float = 30.0,  # Was 60.0 in v2.1.2
    ...
```

**Evidence — Library CLI default** (`.venv/lib/python3.14/site-packages/colab_cli/commands/execution.py:150-153`):
```python
timeout: Annotated[
    Optional[float],
    typer.Option("--timeout", help="Timeout in seconds for code execution"),
] = 30.0,
```

**Better way**: Make timeout configurable via settings (already exists in `core/constants.py:DEFAULT_TIMEOUT = 30`) and ensure the UI passes the user-configured value. The current default of 30s matches upstream CLI but breaks v2.1.2 compatibility — document this.

---

### 5. Folder Download Reimplemented via VM-Side Zip (High)

**Location**: `src/services/colab/files_ops.py:198-289`  
**Changed since 2.1.2**: Yes (new in HEAD)

**Problem**: The upstream library's `ContentsClient` only supports single-file upload/download/list/rm. The app implements folder download by:
1. Running `zip -r` or `shutil.make_archive` on the VM via `exec_code`
2. Downloading the resulting zip via `ContentsClient.download()`
3. Deleting the temp zip on the VM

This is fragile: depends on `zip` binary or Python `shutil`, consumes VM disk/CPU, and leaves temp files on failure.

**Evidence — App code** (`files_ops.py:222-288`):
```python
code = f"""
import subprocess, shutil, os
try:
    if shutil.which('zip'):
        subprocess.run(['zip', '-q', '-r', '{vm_zip_base}.zip', '.'], cwd='{vm_target_dir}', ...)
    else:
        shutil.make_archive('{vm_zip_base}', 'zip', '{vm_target_dir}')
except Exception as e:
    shutil.make_archive('{vm_zip_base}', 'zip', '{vm_target_dir}')
"""
outputs = await service.exec_code(code, ...)
await service.download(remote_path=api_path, local_path=local_path, ...)
await service.rm(path=api_path, ...)
```

**Evidence — Library source** (`.venv/lib/python3.14/site-packages/colab_cli/contents.py`): Only `list_dir`, `upload`, `download`, `rm` — no folder operations.

**Better way**: Keep the VM-side zip approach (no alternative in upstream API) but:
- Add checksum verification after download
- Use streaming download for large folders
- Expose progress callback (already has `on_progress`)
- Consider adding a `download_folder` method to a forked `ContentsClient` for reuse

---

### 6. Token Refresh Logic Duplicated (Medium)

**Location**: `src/services/colab/auth.py:75-158`  
**Changed since 2.1.2**: Refactored but still duplicates upstream logic

**Problem**: The app reimplements the entire OAuth2 token load/refresh/save cycle that the upstream library already provides in `colab_cli.auth._get_google_auth_credentials()` (`.venv/lib/python3.14/site-packages/colab_cli/auth.py:97-151`).

**Evidence — Library source** (`.venv/lib/python3.14/site-packages/colab_cli/auth.py:97-151`):
```python
def _get_google_auth_credentials(config_path: str) -> Credentials:
    ...
    if os.path.exists(TOKEN_CONFIG_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_CONFIG_PATH, PUBLIC_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if not creds:
            creds = _run_remote_flow(client_config)
        with open(TOKEN_CONFIG_PATH, "w") as token_file:
            token_file.write(creds.to_json())
    return creds
```

**Evidence — App code** (`auth.py:110-176`): Reimplements the same flow with `InstalledAppFlow`, manual token file I/O, and `creds.refresh(Request())`.

**Better way**: Call `colab_cli.auth.get_credentials(config_path, provider)` directly and use the returned `AuthorizedSession`. The app's `check_auth_impl` can use the library's token file path (`TOKEN_CONFIG_PATH`) and `Credentials.from_authorized_user_file()` for read-only checks, but should not duplicate the refresh logic.

**Library options to expose**: The library's `get_credentials()` already handles both OAUTH2 and ADC. Just use it.

---

### 7. High-RAM Shape Only Exposed Via `high_mem` Flag (Medium)

**Location**: `src/services/colab/session_ops.py:69-207`  
**Changed since 2.1.2**: Yes (v2.1.2 had no shape parameter; HEAD adds `high_mem`)

**Problem**: The upstream library exposes `Shape` enum (`STANDARD=0`, `HIGH_RAM=1`) and `resolve_assign_shape()` which correctly handles `HIGH_MEM_ONLY_ACCELERATORS` (L4, V5E1, V6E1). The app only exposes a boolean `high_mem` flag, losing the ability to explicitly request STANDARD shape for accelerators that support both.

**Evidence — Library source** (`.venv/lib/python3.14/site-packages/colab_cli/client.py:85-111`):
```python
class Shape(int, Enum):
    STANDARD = 0
    HIGH_RAM = 1

HIGH_MEM_ONLY_ACCELERATORS = frozenset({Accelerator.L4, Accelerator.V5E1, Accelerator.V6E1})

def resolve_assign_shape(accelerator: Optional[Accelerator], *, high_mem: bool = False) -> Optional[Shape]:
    if not high_mem:
        return None
    if accelerator in HIGH_MEM_ONLY_ACCELERATORS:
        return None  # These only have one shape; backend ignores shape=hm
    return Shape.HIGH_RAM
```

**Evidence — App code** (`session_ops.py:100-120`):
```python
shape = resolve_assign_shape(accelerator, high_mem=high_mem)
...
res = st.client.assign(uuid.uuid4(), variant=variant, accelerator=accelerator, shape=shape)
```

**Better way**: The current implementation is correct per upstream logic. The `high_mem` boolean maps to the library's intent. No bug, but the UI (hardware_picker) correctly hides the switch for single-shape accelerators (L4, TPUs).

---

### 8. Drive Mount Reimplemented Via `exec_code` (Medium)

**Location**: `src/services/colab/vm_ops.py:8-35`  
**Changed since 2.1.2**: No (same in v2.1.2)

**Problem**: The upstream library has no Drive mount API. The app implements it by executing `drive.mount()` on the VM via `exec_code` with `intercept_oauth=True` to handle the OAuth flow. This works but is a workaround, not a library feature.

**Evidence — App code** (`vm_ops.py:8-35`):
```python
async def mount_drive_impl(...):
    code = f"from google.colab import drive\ndrive.mount('{path}')"
    outputs = await service.exec_code(
        code, session_name, timeout=600, auth_method=auth_method,
        on_output=on_output, intercept_oauth=True, stdin_hook=stdin_hook
    )
```

**Better way**: This is the only way to mount Drive via the Colab backend. The `intercept_oauth` handling in `execution.py:201-316` correctly implements the credentials propagation flow (dry-run + propagate) that the upstream CLI also uses. No fix needed — just acknowledge it's a custom implementation.

---

### 9. Usage Fetch Swallows All Exceptions (Medium)

**Location**: `src/services/colab/usage_ops.py:42-58`  
**Changed since 2.1.2**: Yes (rebuilt in HEAD)

**Problem**: `get_usage_impl` catches all exceptions and returns `None` (or cached fallback), losing the distinction between auth failure (401), offline, rate-limit (429), and server errors (5xx).

**Evidence — App code** (`usage_ops.py:60-66`):
```python
try:
    fresh = await asyncio.to_thread(_fetch)
except Exception as e:
    logger.warning("Usage fetch failed (%s): %s", type(e).__name__, e)
    if cached_fallback is not None:
        return {**cached_fallback, "cached": True, "reason": "fetch-failed"}
    return None
```

**Evidence — Library source** (`.venv/lib/python3.14/site-packages/colab_cli/client.py:246-250`):
```python
def get_consumption_user_info(self) -> ConsumptionUserInfo:
    url = urljoin(self.colab_domain, f"{TUN_ENDPOINT}/ccu-info")
    ccu = self._issue_request(url, schema=CcuInfo)
    return consumption_user_info_from_tunnel(ccu)
```
The `_issue_request` raises `ColabRequestError` with `response.status_code` for non-2xx.

**Better way**: Catch `ColabRequestError` and inspect `status_code` to set `reason`:
- 401 → "signed-out"
- 429 → "rate-limited"
- 5xx → "server-error"
- Network → "offline"
This allows the UI to show actionable messages.

---

### 10. History Logs Env Keys Only, Not Values (Low)

**Location**: `src/services/colab/execution.py:399-410`  
**Changed since 2.1.2**: Yes (v2.1.2 logged the full prelude with values)

**Problem**: Deliberate divergence from upstream. The upstream `colab_cli.commands.execution` logs the env prelude with plaintext values (see `.venv/lib/python3.14/site-packages/colab_cli/commands/execution.py:265-274`). The app logs only `env_keys` (sorted key names) to avoid leaking secrets.

**Evidence — App code** (`execution.py:399-410`):
```python
st.history.log_event(
    session_name,
    "execution",
    {
        "code": code,
        "env_keys": sorted(env_vars),  # Only key names
        "outputs": outputs,
    },
)
```

**Evidence — Library source** (`.venv/lib/python3.14/site-packages/colab_cli/commands/execution.py:265-274`):
```python
state.history.log_event(
    name,
    "execution",
    {
        "code": code,  # Includes the prelude with os.environ['KEY'] = 'VALUE'
        "outputs": outputs,
        ...
    },
)
```

**Better way**: This is a **security improvement** over upstream. Document it as intentional. The export converters (`colab_cli.converter.export_history`) will need to handle `env_keys` field for notebook reconstruction.

---

### 11. Upload Uses Base64, No Progress for Large Files (Low)

**Location**: `src/services/colab/files_ops.py:53-72` (via `ContentsClient.upload`)  
**Changed since 2.1.2**: No

**Problem**: The upstream `ContentsClient.upload` reads entire file into memory, base64-encodes it, and sends as single JSON payload with `chunk=1`. No streaming/chunked upload for large files. The app inherits this limitation.

**Evidence — Library source** (`.venv/lib/python3.14/site-packages/colab_cli/contents.py:56-72`):
```python
def upload(self, local_path: str, remote_path: str):
    with open(local_path, "rb") as f:
        content = f.read()  # Entire file in memory
    b64_content = base64.b64encode(content).decode("ascii")
    payload = {
        "name": filename,
        "path": remote_path,
        "type": "file",
        "format": "base64",
        "content": b64_content,
        "chunk": 1,  # Always 1 — no multi-chunk support
    }
    return self._request("PUT", remote_path, json_data=payload)
```

**Better way**: For large files, the app could implement chunked upload by splitting the base64 content and sending multiple `chunk=N` requests (if the backend supports it). Currently not exposed in upstream.

---

### 12. Hardware Picker Correctly Mirrors Library Enums (Info)

**Location**: `src/components/hardware_picker.py:105-130`  
**Changed since 2.1.2**: Yes (updated to match library)

**Problem**: None — this is correct. The hardware picker maps UI selections to the library's `Accelerator` enum and respects `HIGH_MEM_ONLY_ACCELERATORS`.

**Evidence — App code** (`hardware_picker.py:61-68`):
```python
def _is_single_shape() -> bool:
    return _selected_accelerator().upper() in ("L4", "V5E1", "V6E1")
```
Matches library's `HIGH_MEM_ONLY_ACCELERATORS = frozenset({Accelerator.L4, Accelerator.V5E1, Accelerator.V6E1})`.

**Evidence — Library source** (`.venv/lib/python3.14/site-packages/colab_cli/client.py:62-70, 92-94`):
```python
class Accelerator(str, Enum):
    NONE = "NONE"
    G4 = "G4"
    T4 = "T4"
    L4 = "L4"
    A100 = "A100"
    H100 = "H100"
    V5E1 = "V5E1"
    V6E1 = "V6E1"
```

---

### 13. Output Mapper Preserves Mime Bundles (Info)

**Location**: `src/services/colab/execution.py:20-66`  
**Changed since 2.1.2**: Yes (new in HEAD — fixes v2.1.2 flattening bug)

**Problem**: v2.1.2's `output_hook` flattened all outputs to `text/plain`, discarding `image/png`, `execution_count`, `metadata`, `transient`. HEAD introduces `_to_cell_output` which preserves the full mime bundle.

**Evidence — App code** (`execution.py:20-66`):
```python
def _to_cell_output(out: dict) -> dict:
    otype = out.get("output_type")
    if otype == "stream":
        entry = {"type": "stream", "text": _join_text(out.get("text", ""))}
        if out.get("name"):
            entry["name"] = out["name"]
        return entry
    if otype in ("execute_result", "display_data"):
        entry = {"type": otype, "data": out.get("data") or {}}
        if out.get("metadata") is not None:
            entry["metadata"] = out["metadata"]
        if otype == "execute_result":
            entry["execution_count"] = out.get("execution_count")
        elif out.get("transient") is not None:
            entry["transient"] = out["transient"]
        return entry
    ...
```

**Evidence — Library source** (`.venv/lib/python3.14/site-packages/colab_cli/runtime.py:220-262`): The upstream `execute_code` returns normalized outputs with `output_type`, `data`, `metadata`, `execution_count`, `traceback` — the app's mapper correctly translates these.

**Better way**: This is the **correct fix** for the v2.1.2 regression. No further action needed.

---

## Additional Observations

### Session Ejection (Commit a073a1c)
The audit scope mentions "session ejection — see commit a073a1c". The current HEAD includes `stop_session_impl` which calls `st.client.unassign(s.endpoint)` (library's `Client.unassign()` at `.venv/lib/python3.14/site-packages/colab_cli/client.py:257-263`). This correctly terminates the server-side assignment. The local record is removed via `st.store.remove()`. No separate "ejection" API exists in the library — `unassign` is the canonical operation.

### Prelude Execution Order
The app correctly follows upstream ordering: `/content` preflight → env prelude → user code (see `execution.py:154-156, 353-357` matching `.venv/lib/python3.14/site-packages/colab_cli/commands/execution.py:217-219, 234-235`).

### Token Expiry Handling
The library's `RuntimeProxyInfo.expires_at()` (`.venv/lib/python3.14/site-packages/colab_cli/client.py:126-130`) computes absolute expiry from `tokenExpiresInSeconds`. The app uses `load_session_fresh()` with `_TOKEN_REFRESH_MARGIN = 5 minutes` (session_ops.py:7) to proactively refresh. This matches the upstream `State.get_session()` pattern (`.venv/lib/python3.14/site-packages/colab_cli/common.py:86-112`).

### GPU/TPU Mapping
The app's `resolve_runtime_options` equivalent in `session_ops.py:100-118` correctly maps to library's `Accelerator` enum. The hardware_picker UI exposes the same options.

---

## Recommendations Priority

| Priority | Action |
|----------|--------|
| **P0** | Fix terminal WebSocket endpoint to use `/colab/tty` or adopt `colab_cli.console.connect_console()` |
| **P0** | Document keep-alive removal as breaking change; verify on-demand token heal covers all paths |
| **P1** | Expose ADC auth provider in UI/settings |
| **P1** | Make execution timeout configurable (already in constants) and pass from UI |
| **P1** | Improve usage fetch error classification (401/429/5xx) |
| **P2** | Add folder download checksum verification |
| **P2** | Consider upstream PR for chunked upload in `ContentsClient` |
| **P3** | Document env_keys-only history logging as security feature |

---

## Files Checked (Read-Only)

- `.venv/lib/python3.14/site-packages/colab_cli/` — entire package source
- `src/services/colab/auth.py`
- `src/services/colab/session_ops.py`
- `src/services/colab/execution.py`
- `src/services/colab/files_ops.py`
- `src/services/colab/logs.py`
- `src/services/colab/terminal_client.py`
- `src/services/colab/usage_ops.py`
- `src/services/colab/vm_ops.py`
- `src/services/colab/text_files.py`
- `src/services/colab/__init__.py`
- `src/screens/session/vm_ops.py`
- `src/screens/session/terminal_panel.py`
- `src/components/hardware_picker.py`
- `tests/services/colab/*.py` (all test files)