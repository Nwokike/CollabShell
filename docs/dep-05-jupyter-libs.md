# Audit: Jupyter Stack Libraries (nbformat, jupyter_client, jupyter_kernel_client, watchdog, pyzmq, traitlets)

**Repo:** `/home/maikel/Desktop/kiri-apps/CollabShell` (branch `main`, HEAD `76a9d4b`)  
**Source of truth:** `/home/maikel/Desktop/kiri-apps/CollabShell/.venv/lib/python3.14/site-packages/`  
**Scope:** nbformat 5.11.1, jupyter_client 8.10.0, jupyter_kernel_client 0.9.0, jupyter_mimetypes 0.2.0, pyzmq 27.2.0, traitlets 5.16.1, watchdog 6.0.0  
**App files audited:** `src/services/ipynb_converter.py`, `src/components/notebook_cell/actions.py`, `src/components/notebook_cell/output.py`, `src/screens/session/notebook_view.py`, `src/services/colab/execution.py`, any watchdog usage

---

## 1. nbformat API Reference (v5.11.1, nbformat v4.5)

### 1.1 Core Entry Points

**File:** `.venv/lib/python3.14/site-packages/nbformat/__init__.py`

| Function | Signature | Path:Line |
|----------|-----------|-----------|
| `reads` | `reads(s: str, as_version: int, capture_validation_error: dict=None, **kwargs) -> NotebookNode` | 66-101 |
| `writes` | `writes(nb: NotebookNode, version: int=NO_CONVERT, capture_validation_error: dict=None, **kwargs) -> str` | 104-137 |
| `read` | `read(fp: file|str, as_version: int, capture_validation_error: dict=None, **kwargs) -> NotebookNode` | 140-174 |
| `write` | `write(nb: NotebookNode, fp: file|str, version: int=NO_CONVERT, capture_validation_error: dict=None, **kwargs) -> None` | 177-211 |
| `validate` | `validate(nbdict: Any, ref: str=None, version: int=None, version_minor: int=None, relax_add_props: bool=False, nbjson: Any=None) -> None` | 388-434 |
| `iter_validate` | `iter_validate(nbdict=None, ref=None, version=None, version_minor=None, relax_add_props=False, nbjson=None, strip_invalid_metadata=False) -> Generator[ValidationError]` | 589-649 |
| `normalize` | `normalize(nbdict: Any, version: int=None, version_minor: int=None, *, relax_add_props: bool=False, strip_invalid_metadata: bool=False) -> tuple[int, Any]` | 264-316 |
| `convert` | `convert(nb, to_version)` | `.converter:47` |
| `from_dict` | `from_dict(d: dict) -> NotebookNode` | `.notebooknode:73` |

### 1.2 NotebookNode

**File:** `.venv/lib/python3.14/site-packages/nbformat/notebooknode.py:14-84`

```python
class NotebookNode(Struct):  # dict-like with attribute access
    def __setitem__(self, key, value):  # auto-wraps Mapping to NotebookNode
    def __deepcopy__(self, memo):       # optimized for notebooks
    def update(self, *args, **kwargs):  # dict-like update
```

### 1.3 v4 Factory Functions

**File:** `.venv/lib/python3.14/site-packages/nbformat/v4/nbbase.py:44-171`

| Function | Signature | Notes |
|----------|-----------|-------|
| `new_notebook` | `new_notebook(**kwargs) -> NotebookNode` | validates via `validate(nb)` |
| `new_code_cell` | `new_code_cell(source="", **kwargs) -> NotebookNode` | sets `execution_count=None`, `outputs=[]` |
| `new_markdown_cell` | `new_markdown_cell(source="", **kwargs) -> NotebookNode` | |
| `new_raw_cell` | `new_raw_cell(source="", **kwargs) -> NotebookNode` | |
| `new_output` | `new_output(output_type, data=None, **kwargs) -> NotebookNode` | populates defaults per type |
| `output_from_msg` | `output_from_msg(msg: dict) -> NotebookNode` | converts kernel IOPub msg to output |

**`new_output` defaults by type:**
- `stream`: `name="stdout"`, `text=""`
- `display_data`: `metadata={}`, `data={}`
- `execute_result`: `metadata={}`, `data={}`, `execution_count=None`
- `error`: `ename="NotImplementedError"`, `evalue=""`, `traceback=[]`

**`output_from_msg` handles msg_types:** `execute_result`, `stream`, `display_data`, `error`

### 1.4 Validation & Normalization

**File:** `.venv/lib/python3.14/site-packages/nbformat/validator.py`

- `validate(nbdict, ref=None, version=4, version_minor=5, relax_add_props=False)` — raises `ValidationError` on failure
- `iter_validate(...)` — yields all errors
- `normalize(nbdict, version=4, version_minor=5, relax_add_props=False, strip_invalid_metadata=False)` — returns `(changes_count, normalized_dict)`
- `isvalid(nbdict, ...)` — returns `bool`

**Schema (v4.5):** `.venv/lib/python3.14/site-packages/nbformat/v4/nbformat.v4.5.schema.json`

Key schema constraints:
- **code_cell** required: `id`, `cell_type`, `metadata`, `source`, `outputs`, `execution_count` (integer or null)
- **output** oneOf: `execute_result`, `display_data`, `stream`, `error`
- **execute_result** required: `output_type`, `execution_count`, `data` (mimebundle), `metadata`
- **display_data** required: `output_type`, `data`, `metadata`
- **stream** required: `output_type`, `name` (stdout/stderr), `text` (string or array)
- **error** required: `output_type`, `ename`, `evalue`, `traceback` (array of strings)
- `additionalProperties: false` for all defined types (strict)
- `relax_add_props=True` allows extra properties

---

## 2. jupyter_client API Reference (v8.10.0)

### 2.1 KernelManager

**File:** `.venv/lib/python3.14/site-packages/jupyter_client/manager.py:121-900`

```python
class KernelManager(ConnectionFileMixin):
    # Key traits
    kernel_name: Unicode = "python3"
    kernel_spec_manager: Instance(KernelSpecManager)
    shutdown_wait_time: Float = 5.0
    autorestart: Bool = True
    transport_encryption: CaselessStrEnum = "disabled"  # "disabled"|"auto"|"required"
    client_class: DottedObjectName = "jupyter_client.blocking.BlockingKernelClient"
    
    # Key methods
    def start_kernel(self, **kw) -> None              # launches kernel process
    def restart_kernel(self, now=False, newports=False, **kw) -> None
    def shutdown_kernel(self, now=False, restart=False) -> None
    def interrupt_kernel(self) -> None                 # SIGINT or interrupt_request
    def is_alive(self) -> bool
    def client(self, **kwargs) -> BlockingKernelClient # create connected client
    def request_shutdown(self, restart=False) -> None  # polite shutdown via control
    def finish_shutdown(self, waittime=None, pollinterval=0.1, restart=False) -> None
    
    # Async variants
    async def _async_start_kernel(self, **kw) -> None
    async def _async_restart_kernel(self, now=False, newports=False, **kw) -> None
    async def _async_shutdown_kernel(self, now=False, restart=False) -> None
```

### 2.2 BlockingKernelClient

**File:** `.venv/lib/python3.14/site-packages/jupyter_client/blocking/client.py:33-70`

```python
class BlockingKernelClient(KernelClient):
    # Channel access (blocking)
    get_shell_msg = run_sync(KernelClient._async_get_shell_msg)
    get_iopub_msg = run_sync(KernelClient._async_get_iopub_msg)
    get_stdin_msg = run_sync(KernelClient._async_get_stdin_msg)
    get_control_msg = run_sync(KernelClient._async_get_control_msg)
    wait_for_ready = run_sync(KernelClient._async_wait_for_ready)
    
    # Request/reply (blocking)
    execute = reqrep(wrapped, KernelClient.execute)
    complete = reqrep(wrapped, KernelClient.complete)
    inspect = reqrep(wrapped, KernelClient.inspect)
    kernel_info = reqrep(wrapped, KernelClient.kernel_info)
    comm_info = reqrep(wrapped, KernelClient.comm_info)
    history = reqrep(wrapped, KernelClient.history)
    shutdown = reqrep(wrapped, KernelClient.shutdown, channel="control")
    
    # Interactive execution with streaming
    execute_interactive = run_sync(KernelClient._async_execute_interactive)
    is_alive = run_sync(KernelClient._async_is_alive)
```

### 2.3 KernelClient (Base)

**File:** `.venv/lib/python3.14/site-packages/jupyter_client/client.py:77-855`

Key methods:
- `execute(code, silent=False, store_history=True, user_expressions=None, allow_stdin=None, stop_on_error=True) -> str` (returns msg_id)
- `execute_interactive(code, ..., output_hook=None, stdin_hook=None, timeout=None) -> dict` (returns reply)
- `start_channels(shell=True, iopub=True, stdin=True, hb=True, control=True)`
- `stop_channels()`
- `input(string) -> None` (send stdin reply)
- `shutdown(restart=False) -> str` (msg_id on control)
- `_output_hook_default(msg)` — handles stream/display_data/execute_result/error

**`execute_interactive` output_hook receives raw IOPub messages** with `msg["header"]["msg_type"]`:
- `stream`: `content = {"name": "stdout|stderr", "text": "..."}`
- `execute_result`: `content = {"execution_count": int, "data": {...}, "metadata": {...}}`
- `display_data`: `content = {"data": {...}, "metadata": {...}, "transient": {...}}`
- `error`: `content = {"ename": "...", "evalue": "...", "traceback": [...]}`
- `status`: `content = {"execution_state": "busy|idle|starting"}`
- `clear_output`: `content = {"wait": bool}`

---

## 3. jupyter_kernel_client API Reference (v0.9.0)

### 3.1 KernelClient (HTTP/WebSocket)

**File:** `.venv/lib/python3.14/site-packages/jupyter_kernel_client/client.py:108-632`

```python
class KernelClient(LoggingConfigurable):
    def __init__(self, kernel_id: str=None, log: Logger=None, **kwargs):
        # kwargs passed to KernelHttpManager: server_url, token, username
    
    def execute(self, code: str, silent: bool=False, store_history: bool=True,
                user_expressions: dict=None, allow_stdin: bool=False,
                stop_on_error: bool=True, timeout: float=REQUEST_TIMEOUT,
                stdin_hook: Callable=None, variables: dict=None) -> dict:
        # Returns: {"execution_count": int|None, "outputs": list[dict], "status": "ok|error"}
    
    def execute_interactive(self, code: str, ..., output_hook: Callable=None,
                            stdin_hook: Callable=None, variables: dict=None) -> dict:
        # output_hook called with each output dict
    
    def start(self, name: str="python3", path: str=None, timeout: float=REQUEST_TIMEOUT) -> None
    def stop(self, shutdown_kernel: bool=None, shutdown_now: bool=True, timeout: float=REQUEST_TIMEOUT) -> None
    def interrupt(self, timeout: float=REQUEST_TIMEOUT) -> None
    def is_alive(self, timeout: float=REQUEST_TIMEOUT) -> bool
    def restart(self, timeout: float=REQUEST_TIMEOUT) -> None
```

### 3.2 Output Hook (Normalization)

**File:** `.venv/lib/python3.14/site-packages/jupyter_kernel_client/client.py:24-105`

```python
def output_hook(outputs: list[dict], message: dict) -> set[int]:
    msg_type = message["header"]["msg_type"]
    content = message["content"]
    
    if msg_type == "execute_result":
        output = {"output_type": msg_type, "metadata": content.get("metadata"),
                  "data": content.get("data"), "execution_count": content.get("execution_count")}
    elif msg_type == "stream":
        output = {"output_type": msg_type, "name": content.get("name"),
                  "text": content.get("text")}
    elif msg_type == "display_data":
        output = {"output_type": msg_type, "metadata": content.get("metadata"),
                  "data": content.get("data"), "transient": content.get("transient")}
    elif msg_type == "error":
        output = {"output_type": msg_type, "ename": content.get("ename"),
                  "evalue": content.get("evalue"), "traceback": content.get("traceback")}
    elif msg_type == "clear_output":
        outputs.clear()
        return set(range(size))
    elif msg_type == "update_display_data":
        # matches by display_id in transient
        ...
```

---

## 4. watchdog API Reference (v6.0.0)

### 4.1 Observer

**File:** `.venv/lib/python3.14/site-packages/watchdog/observers/__init__.py:49-91`

```python
Observer = _get_observer_cls()  # Platform-specific: Inotify/FSEvents/Kqueue/WinApi/Polling

class Observer(BaseObserver):
    def __call__(self, *, timeout: float = ...) -> BaseObserver: ...
    def schedule(self, event_handler, path, recursive=False) -> Watch
    def unschedule(self, watch) -> None
    def start(self) -> None
    def stop(self) -> None
    def join(self, timeout=None) -> None
```

### 4.2 Event Handler

**File:** `.venv/lib/python3.14/site-packages/watchdog/events.py` (not shown, standard)

```python
class FileSystemEventHandler:
    def on_created(self, event): ...
    def on_deleted(self, event): ...
    def on_modified(self, event): ...
    def on_moved(self, event): ...
```

Events: `FileCreatedEvent`, `FileDeletedEvent`, `FileModifiedEvent`, `FileMovedEvent` with `src_path`, `dest_path`, `is_directory`.

---

## 5. pyzmq / traitlets (Supporting Stack)

### 4.1 pyzmq (v27.2.0)

- `zmq.Context()` — socket context
- `zmq.Socket` types: `REQ`, `REP`, `PUB`, `SUB`, `DEALER`, `ROUTER`, `PULL`, `PUSH`
- `zmq.Poller()` / `zmq.asyncio.Poller()` — async I/O multiplexing
- `zmq.CurveZMQ` — transport encryption (requires libsodium)

### 4.2 traitlets (v5.16.1)

- `HasTraits` — base class for configurable objects
- Trait types: `Unicode`, `Int`, `Float`, `Bool`, `Dict`, `List`, `Instance`, `Type`, `DottedObjectName`, `CaselessStrEnum`, `Any`
- Decorators: `@default`, `@validate`, `@observe`, `@observe_compat`
- `Configurable` — integrates with Jupyter config system

---

## 6. App Usage Analysis — Gap Tables

### 6.1 nbformat: ipynb_converter.py

| # | Severity | App Location | Library Source | Problem | Better Way |
|---|----------|--------------|----------------|---------|------------|
| 1 | **critical** | `ipynb_converter.py:48-60` | `nbformat/v4/nbbase.py:117-130` | `cells_to_ipynb` derives `execution_count` from outputs only, ignores cell-level `execution_count` field. A cell with `execution_count: 5` but only stream outputs loses its count on export. | Prefer `cell.get("execution_count")` if present and not null; fallback to derived. |
| 2 | **high** | `ipynb_converter.py:32-76` | `nbformat/validator.py:388-434` | No `nbformat.validate()` call after constructing notebook. Invalid output `data` keys (e.g., custom MIME types) pass through but fail downstream (Jupyter, nbconvert). | Call `nbformat.validate(nb)` after `cells_to_ipynb`; or strip unknown MIME types to known set. |
| 3 | **high** | `ipynb_converter.py:278-319` | `nbformat/v4/nbformat.v4.5.schema.json` | `_outputs_to_ipynb` accepts arbitrary keys in `data`/`metadata`. Schema has `additionalProperties: false` — unknown MIME types raise `ValidationError`. | Validate or sanitize `data` keys to standard set: `text/plain`, `text/html`, `image/png`, `image/jpeg`, `image/svg+xml`, `application/json`, `application/javascript`. |
| 4 | **high** | `ipynb_converter.py:322-359` | `nbformat/v4/nbbase.py:73-114` | `_outputs_from_ipynb` doesn't handle `update_display_data` or `clear_output` msg_types from kernel. `output_from_msg` raises `ValueError` for unrecognized types. | Add handling for `update_display_data` (maps to `display_data` with `transient.display_id`) and `clear_output` (emits special marker). |
| 5 | **medium** | `ipynb_converter.py:272-276` | `nbformat/v4/nbformat.v4.5.schema.json:360-364` | `_as_text_lines` wraps single string in list `[""]` for empty text. nbformat expects stream `text` as array of lines; empty should be `[]` or `[""]`. | Return `[]` for empty/None text; nbformat accepts both. |
| 6 | **medium** | `ipynb_converter.py:115-125` | `nbformat/v4/nbbase.py:117-130` | `cells_to_py` skips empty cells (correct per percent format). But `py_to_cells` generates fresh UUIDs — breaks ID stability for round-trips not using `merge_script_cells`. | Document that `py_to_cells` IDs are ephemeral; always use `merge_script_cells` for round-trips. |
| 7 | **medium** | `ipynb_converter.py:103-125` | `nbformat/v4/nbbase.py:133-144` | `py_to_cells` treats `# %% [markdown] Title` as markdown with title as body. But `# %% [markdown]` alone creates empty markdown cell that `cells_to_py` skips — asymmetry. | Accept `# %% [markdown]` with no body as valid empty markdown cell; represent in script. |
| 8 | **low** | `ipynb_converter.py:79-100` | `nbformat/v4/nbbase.py:133-144` | `ipynb_to_cells` generates new UUIDs for imported cells. Original cell IDs from `.ipynb` are discarded — breaks external references (e.g., assistant step→cell links). | Preserve `id` from IPYNB cell when present: `cell["id"] = ipynb_cell.get("id", str(uuid.uuid4()))`. |
| 9 | **info** | `ipynb_converter.py:1` | `nbformat/__init__.py:18-36` | Exports `NO_CONVERT`, `NotebookNode`, `validate`, `reads`, `writes`, `read`, `write`, `convert`, `from_dict` — app only uses `cells_to_ipynb`, `ipynb_to_cells`, `cells_to_py`, `py_to_cells`. | Not an issue; app provides higher-level API. |

---

### 6.2 Kernel Execution: colab/execution.py

| # | Severity | App Location | Library Source | Problem | Better Way |
|---|----------|--------------|----------------|---------|------------|
| 10 | **critical** | `execution.py:190-199` | `jupyter_client/client.py:448-604` | `output_hook` receives normalized output dict from `colab_cli.runtime.execute_code` (which uses `jupyter_kernel_client.output_hook`), NOT raw IOPub messages. The hook expects `output_type` not `msg_type`. Code correctly handles this but comment says "raw messages" — misleading. | Update comment: hook receives normalized output dicts with `output_type`, `data`, `text`, `execution_count`, `traceback`, etc. |
| 11 | **high** | `execution.py:24-66` | `jupyter_client/client.py:448-604` | `_to_cell_output` maps `execute_result`/`display_data` but **drops `transient` field** for `display_data`. `transient` contains `display_id` for `update_display_data` correlation. | Preserve `transient` for `display_data`: `entry["transient"] = out.get("transient", {})`. |
| 12 | **high** | `execution.py:57-63` | `jupyter_client/client.py:589-592` | `status` messages (`execution_state: busy/idle`) are not handled. The `output_hook` in `colab_cli` stops on `status` idle but doesn't pass status to app hook. App cannot show "running" indicator from kernel. | If kernel status needed, add `status` passthrough or poll `kernel_info`/`is_alive`. |
| 13 | **high** | `execution.py:201-318` | `jupyter_kernel_client/client.py:55-132` | `drivefs_hook` duplicates library's `drivefs_hook` (colab_cli/commands/automation.py:55-132). App version adds retry loop (6×2s) — **improvement** but duplicated logic. | Extract to shared utility; contribute retry loop upstream. |
| 14 | **medium** | `execution.py:356-362` | `jupyter_client/client.py:448-604` | `runtime.execute_code` called with `allow_stdin=intercept_oauth or (stdin_hook is not None)`. If `intercept_oauth=True` but no `stdin_hook`, `allow_stdin=True` enables raw `input()` in kernel — may hang if no UI hook. | Only set `allow_stdin=True` when `stdin_hook` is actually provided. |
| 15 | **medium** | `execution.py:90-134` | `colab_cli/commands/execution.py:41-62` | Env var validation regex `^[A-Za-z_][A-Za-z0-9_]*$` duplicated to avoid importing `execution.py` (pulls `termios` on Windows). Library has `_parse_env_vars`/`_build_env_prelude`. | Extract env parsing to non-POSIX module in library; import safely. |
| 16 | **medium** | `execution.py:144-157` | `jupyter_client/manager.py:527-535` | Preflight code `import os; os.makedirs('/content', exist_ok=True); os.chdir('/content')` executed **before** env prelude. Library's `colab run` does same. Correct ordering. | No change needed. |
| 17 | **low** | `execution.py:182-188` | `jupyter_client/client.py:488-492` | `s.running = "exec(code)"` and `last_execution` tracking — app-specific, not in library. OK. | No change needed. |
| 18 | **info** | `execution.py:24-66` | `jupyter_kernel_client/client.py:24-105` | `_to_cell_output` preserves rich mime bundles (`data` dict) — correct. Earlier versions flattened to `text/plain` only. | No change needed. |

---

### 6.3 Notebook UI: notebook_view.py, notebook_cell/output.py, notebook_cell/actions.py

| # | Severity | App Location | Library Source | Problem | Better Way |
|---|----------|--------------|----------------|---------|------------|
| 19 | **critical** | `notebook_cell/output.py:30-52` | `nbformat/v4/nbformat.v4.5.schema.json:311-343` | `parse_outputs_to_controls` handles `image/png` and `text/plain` only. **Ignores**: `text/html`, `image/jpeg`, `image/svg+xml`, `application/json`, `application/javascript`, `text/markdown`, `text/latex`. Rich outputs (plots, HTML, JSON) silently dropped. | Add handlers for all standard MIME types. Use `flet.Markdown` for `text/html`/`text/markdown`, `flet.Image` for `image/jpeg`/`image/svg+xml`, `flet.Text` with syntax highlight for `application/json`/`application/javascript`. |
| 20 | **high** | `notebook_cell/output.py:8-53` | `jupyter_client/client.py:569-592` | Stream `text` may be string or list (nbformat). Code assumes string: `text = out.get("text", "")`. `_join_text` helper exists in `execution.py` but not reused here. | Use `_join_text` from `execution.py` or duplicate: `text = "".join(text) if isinstance(text, list) else str(text)`. |
| 21 | **high** | `notebook_view.py:420-430` | `jupyter_client/client.py:448-604` | `_append_output` accepts `text_or_dict` — if dict, assumes it's already normalized output. But kernel IOPub messages have `msg_type`/`content`. The `on_output` callback from `execution.py` passes `_to_cell_output` result (normalized). Works but fragile if callback changes. | Document contract: `on_output` receives normalized output dict (`output_type`, `data`, `text`, etc.), not raw IOPub message. |
| 22 | **high** | `notebook_view.py:445-475` | `jupyter_client/client.py:448-604` | `_run_cell` clears `cell.outputs` before execution. If execution fails before any output, cell shows empty — no error indicator. Error from `exec_code_impl` caught and appended as `{"type": "error", "traceback": [str(ex)]}`. But **kernel errors** (status=error with error output) arrive via `on_output` and are appended correctly. Works but two error paths. | Unify: always append via `on_output`; don't pre-clear until first output arrives. |
| 23 | **medium** | `notebook_view.py:169-193` | `nbformat/validator.py:264-385` | `enforce_image_budget` approximates image size by `len(base64_string)`. Base64 is ~33% overhead; actual decoded bytes = `len(b64) * 3/4`. Budget of 4MB base64 ≈ 3MB decoded. | Decode to check actual bytes: `len(base64.b64decode(b64))` or use `len(b64) * 3 // 4`. |
| 24 | **medium** | `notebook_cell/actions.py:169-225` | `nbformat/v4/nbformat.v4.5.schema.json:311-343` | `copy_output` handles `stream`, `error`, `execute_result`, `display_data` but **not** `update_display_data` or `clear_output`. Also assumes `text/plain` for rich outputs — drops images. | Add `update_display_data` (treat as `display_data`), handle `clear_output` (return empty), extract all MIME types. |
| 25 | **medium** | `notebook_view.py:1029-1059` | `nbformat/__init__.py:104-137` | `_export_as` calls `cells_to_ipynb` then `json.dumps`. No `nbformat.validate()` before write. Invalid notebooks may be exported. | Call `nbformat.validate(nb)` after `cells_to_ipynb`; catch `ValidationError` and warn. |
| 26 | **medium** | `notebook_view.py:1123-1159` | `nbformat/__init__.py:66-102` | `_import_ipynb` uses `ipynb_to_cells` which calls `_outputs_from_ipynb`. No validation of imported notebook. Malformed notebooks (missing required fields) may crash or produce corrupt cells. | Call `nbformat.validate(ipynb)` before `ipynb_to_cells`; or wrap in try/except. |
| 27 | **low** | `notebook_view.py:419-429` | `jupyter_client/client.py:448-604` | `_MAX_OUTPUT_ENTRIES = 5000` caps outputs per cell. nbformat has no such limit. App-specific policy. | Document as app limit; consider making configurable. |
| 28 | **low** | `notebook_view.py:363-417` | `jupyter_client/manager.py:848-881` | Kernel lifecycle: `restart_kernel` called via `services.colab.restart_kernel` (wraps `colab_cli`). No direct `jupyter_client` usage. OK. | No change needed. |
| 29 | **info** | `notebook_cell/output.py:1-53` | `jupyter_client/client.py:261-272` | Uses `parse_ansi_to_flet_text` for stream/error text. Correct for ANSI-colored terminal output. | No change needed. |

---

### 6.4 Watchdog Usage

| # | Severity | App Location | Library Source | Problem | Better Way |
|---|----------|--------------|----------------|---------|------------|
| 30 | **info** | (none found) | `watchdog/observers/__init__.py:89` | **No watchdog usage found** in `src/services/`, `src/components/`, `src/screens/session/`. `router_watchdog.py` uses custom polling, not `watchdog.Observer`. | If file watching needed (e.g., auto-reload on .ipynb change), use `Observer` with `FileSystemEventHandler`. |

---

## 7. Library Options Not Exposed by App

### 7.1 nbformat

| Feature | Location | App Status |
|---------|----------|------------|
| `nbformat.read(fp, as_version=4)` / `write(nb, fp)` | `__init__.py:140-211` | App uses custom JSON read/write via `storage_service`; could use nbformat directly for validation. |
| `nbformat.validate(nb, relax_add_props=True)` | `validator.py:388-434` | **Not used** — app never validates notebooks before export/import. |
| `nbformat.normalize(nb, strip_invalid_metadata=True)` | `validator.py:264-316` | **Not used** — could sanitize imported notebooks. |
| `nbformat.convert(nb, to_version)` | `converter.py` | **Not used** — app assumes v4.5. |
| `nbformat.v4.new_output(output_type, ...)` | `v4/nbbase.py:44-70` | App builds output dicts manually; could use factory for correctness. |
| `nbformat.v4.output_from_msg(msg)` | `v4/nbbase.py:73-114` | **Not used** — app uses `colab_cli`/`jupyter_kernel_client` normalization instead. |
| `NotebookNode` attribute access | `notebooknode.py:14-84` | App uses plain dicts; `CellData` is observable wrapper. |
| `validate(nb, "code_cell")` / `validate(nb, "execute_result")` | `validator.py:388-434` | **Not used** — could validate individual cells/outputs. |

### 7.2 jupyter_client

| Feature | Location | App Status |
|---------|----------|------------|
| `KernelManager.start_kernel()` / `restart_kernel()` / `shutdown_kernel()` | `manager.py:514-691` | App uses `colab_cli` for remote kernel management; local `jupyter_client` not used. |
| `BlockingKernelClient.execute_interactive(output_hook=...)` | `blocking/client.py:69` | **Not used** — app uses `colab_cli.runtime.ColabRuntime.execute_code`. |
| `KernelClient.kernel_info()` / `complete()` / `inspect()` / `history()` | `client.py:674-772` | **Not used** — could enable autocomplete, introspection, history in notebook UI. |
| `KernelClient.comm_info()` / `comm_open()` / `comm_msg()` | `client.py:785-830` | **Not used** — could support Jupyter comms (widgets). |
| `KernelManager.autorestart` / `shutdown_wait_time` | `manager.py:297-252` | Not configured; app manages kernel lifecycle via Colab API. |
| `transport_encryption="auto|required"` (CurveZMQ) | `manager.py:162-197` | Not used; Colab uses token auth over HTTPS/WSS. |
| `KernelClient.allow_stdin` / `stdin_hook` | `client.py:118, 448-604` | App provides custom `stdin_hook` via `execution.py`; correct. |

### 7.3 jupyter_kernel_client

| Feature | Location | App Status |
|---------|----------|------------|
| `KernelClient.execute_interactive(output_hook=...)` | `client.py:313-374` | App uses `colab_cli.runtime.ColabRuntime.execute_code` which wraps this. |
| `KernelClient.get_variable()` / `set_variable()` / `list_variables()` | `client.py:443-580` | **Not used** — could enable variable explorer in UI. |
| `KernelClient.get_variable_mimetypes()` | `client.py:582-631` | **Not used** — could show rich variable representations. |
| `KernelClient.kernel_info` property | `client.py:206-216` | **Not used** — could show kernel language/version in UI. |
| `HistoryLogger` / `convert_history_to_ipynb()` | `history.py:21-65`, `converter.py:22-184` | App has own `history.py` and `conversation_service`; could export history as `.ipynb`. |

### 7.4 watchdog

| Feature | Location | App Status |
|---------|----------|------------|
| `Observer` + `FileSystemEventHandler` | `observers/__init__.py:89`, `events.py` | **Not used** — no file system watching in app. Could watch `.ipynb` files for external edits. |
| `PollingObserver` (cross-platform fallback) | `observers/polling.py` | **Not used** — works everywhere including network mounts. |

### 7.5 jupyter_mimetypes

| Feature | Location | App Status |
|---------|----------|------------|
| `serialize_object(value)` / `deserialize_object(data, metadata)` | `jupyter_mimetypes/__init__.py` | **Not used** — `jupyter_kernel_client` uses this internally for variable transfer. App could use for custom object serialization. |

---

## 8. Cross-Reference with Existing Audits

| Doc | Related Finding | Status |
|-----|----------------|--------|
| `audit-05-notebook-files-storage.md#1` | `cells_to_ipynb` loses `execution_count` | **Confirmed** — #1 above |
| `audit-05-notebook-files-storage.md#3` | `_outputs_from_ipynb` no validation | **Confirmed** — #2, #3 above |
| `audit-05-notebook-files-storage.md#6` | `py_to_cells` fresh UUIDs | **Confirmed** — #6 above |
| `dep-03-colab-libs.md#10` | `exec_code_impl` reimplements `colab_cli` | **Confirmed** — #10-#18 above |
| `dep-03-colab-libs.md#11` | `drivefs_hook` duplication | **Confirmed** — #13 above |
| `dep-03-colab-libs.md#23` | Env var parsing duplication | **Confirmed** — #15 above |

---

## 9. Summary: Critical/High Priority Fixes

| # | Fix | Files |
|---|-----|-------|
| 1 | Preserve cell-level `execution_count` in `cells_to_ipynb` | `ipynb_converter.py:48-60` |
| 2 | Add `nbformat.validate()` after notebook construction (export/import) | `ipynb_converter.py:32-76`, `notebook_view.py:1029-1159` |
| 3 | Sanitize/validate MIME types in output conversion | `ipynb_converter.py:278-359`, `notebook_cell/output.py:30-52` |
| 4 | Handle all standard MIME types in output rendering (`text/html`, `image/jpeg`, `image/svg+xml`, `application/json`, `application/javascript`) | `notebook_cell/output.py:30-52` |
| 5 | Fix stream text handling (string vs list) in `parse_outputs_to_controls` | `notebook_cell/output.py:8-53` |
| 6 | Preserve `transient` field for `display_data` outputs | `execution.py:24-66` |
| 7 | Preserve original cell IDs on `.ipynb` import | `ipynb_converter.py:79-100` |
| 8 | Add `update_display_data` and `clear_output` handling | `ipynb_converter.py:322-359`, `notebook_cell/actions.py:169-225` |

---

*Generated by audit of `.venv/lib/python3.14/site-packages/` (nbformat 5.11.1, jupyter_client 8.10.0, jupyter_kernel_client 0.9.0, jupyter_mimetypes 0.2.0, pyzmq 27.2.0, traitlets 5.16.1, watchdog 6.0.0) and app source at HEAD `76a9d4b`.*
