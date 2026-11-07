# Audit 09 — AI Step Output Rendering (read-only)

**Repo:** `/home/maikel/Desktop/kiri-apps/ColabShell` (branch `main`, HEAD `76a9d4b`)
**Task:** Read-only audit of why an AI tool step (e.g. `_exec`, `read_terminal`) renders an
EMPTY output area with only a copy button, instead of the same rich output rendering as the
notebook screen. Proposed redesign: step row actions = [copy] + [open in terminal | open in
notebook] (whichever applies); output area uses the shared `parse_outputs_to_controls` renderer
so images/plots/html/json render exactly like the notebook.

Cross-checked: `docs/audit-01-ai-assistant.md`, `docs/dep-05-jupyter-libs.md`.

---

## 1. Current rendering trace (file:line) + why the output is empty

### 1.1 The root cause: `outputs` never leaves the JSON-encoded `result` string

The assistant renders step rows via `build_ai_step_output(...)` in
`src/screens/assistant_view.py:1290-1298`, passing `outputs=row.get("outputs", [])`.
That `outputs` list is populated in `ChatSession._on_tool_done`
(`src/screens/assistant_view.py:806-824`):

```python
# assistant_view.py:806-824
def _on_tool_done(self, name: str, payload: dict) -> None:
    result = payload.get("result", "")
    error = payload.get("error")
    args = payload.get("args") or {}
    data = {
        "id": str(payload.get("id") or "") or _running_step_id(self._current),
        "name": name,
        "label": _pretty_label(name, args),
        "result": result,
        "refs": _cell_refs({"name": name, "result": result}),
        # Include outputs for rich rendering
        "outputs": payload.get("outputs", []),      # <-- ALWAYS []  (see below)
    }
    self._emit("step_error" if error else "step_done", {**data, "error": error})
```

`payload.get("outputs", [])` is `[]` because the step payload never carries an `outputs`
field. Tracing upstream:

- `kani_backend.tool_specs` (`src/services/kani_backend.py:143-179`) builds the step payload
  as exactly `{"name", "id", "args", "result", "error"}` (docstring line 130). There is no
  `outputs` key, so `payload.get("outputs", [])` is `[]`.
- `ai_service._step_emitter` (`src/services/ai_service.py:237-267`) forwards only
  `{"id", "args", "result", "error"}` to `_on_tool_done` (line 257-264). No `outputs`.
- The rich outputs are produced by the tools themselves:
  - `ai_tools._exec` (`src/services/ai_tools.py:134-200`) collects `outputs: list[dict]`
    during execution and, when non-empty, wraps them INSIDE the result string:
    ```python
    # ai_tools.py:194-199
    out = "".join(chunks).strip()
    result = _clip(out) if out else "(no output)"
    if outputs:
        result = json.dumps({"text": result, "outputs": outputs})   # <-- trapped in string
    return result
    ```
  - `ai_tools.read_terminal` (`src/services/ai_tools.py:259-283`) does the same:
    ```python
    # ai_tools.py:276-280
    result = _clip_text(text) if text.strip() else "(terminal is empty)"
    outputs = [{"type": "stream", "text": text}] if text.strip() else []
    return json.dumps({"text": result, "outputs": outputs})
    ```

So the `outputs` list is **trapped inside the JSON-encoded `result` string**. Nothing parses
that string back into `payload["outputs"]`. Consequently:

- `row["outputs"] == []` for every step row.
- `_render_assistant` calls `build_ai_step_output(outputs=row.get("outputs", []))` with an
  empty list.
- `build_ai_step_output` calls `parse_outputs_to_controls([])` → `[]` → the output area is
  empty. The row shows only the label/outcome text and the action buttons (copy + possibly
  open terminal/notebook), but **no rendered output** — exactly the reported symptom: an
  empty output area with only a copy button.

Additionally `row["result"]` holds the raw JSON string `{"text": ..., "outputs": [...]}`,
which leaks into the step-row outcome label (see `_render_assistant` line 1275-1279), so the
label shows garbled JSON instead of a clean short outcome.

### 1.2 What `build_ai_step_output` does with `outputs`

`src/components/ai_step_output.py:19-111` (`build_ai_step_output`):

```python
def build_ai_step_output(tool_name, outputs, state, on_open_terminal=None,
                         on_open_notebook=None, on_copy=None) -> ft.Control:
    output_controls = parse_outputs_to_controls(outputs)   # line 41 — shared notebook renderer
    ...
```

It correctly delegates to the shared notebook-cell renderer `parse_outputs_to_controls`
(`src/components/notebook_cell/output.py:32-101`), which handles `stream`, `error`,
`clear_output`, `execute_result`/`display_data`/`update_display_data`, images (PNG/JPEG/GIF/
WEBP), SVG, and text MIME types (`application/json`, `text/html`, `text/markdown`,
`text/plain`, `application/javascript`). The renderer itself is fine; it simply never
receives any outputs.

There is also `build_live_tool_output` (`ai_step_output.py:114-174`) for streaming live
tool output. It renders plain `text` (not `outputs`) and is **not** currently wired into the
step-row render path — live output is shown inline in the label via `row["live_output"]`
(`assistant_view.py:1280-1287`).

### 1.3 The operator-precedence bug (audit-01 #12)

`src/components/ai_step_output.py:46`:

```python
if tool_name == "_exec" and state in ("running", "done") or tool_name == "read_terminal" and state in ("running", "done"):
```

Python precedence (`and` binds tighter than `or`) makes this
`(tool_name == "_exec" and state in (...)) or (tool_name == "read_terminal" and state in (...))`.
Functionally it only yields "Open Terminal" for `_exec`/`read_terminal` in running/done, and
"Open Notebook" for `read_notebook` in running/done (`ai_step_output.py:55-63`). audit-01
flagged it as hard to read / easy to misread and recommended
`tool_name in ("_exec", "read_terminal") and state in (...)` — but the deeper problem for this
audit is **which open action to show and whether to show it at all** depends on
`session_mode` (notebook vs terminal), which the component has no access to.

### Summary of why output is empty

| Step | Location | What happens | Why output ends up empty |
|------|----------|--------------|--------------------------|
| Tool produces outputs | `ai_tools.py:134-200` `_exec`, `:259-283` `read_terminal` | `outputs` list built, then JSON-encoded into `result` string | `outputs` is trapped inside a string, not a payload field |
| kani step payload | `kani_backend.py:143-149` | Payload = `{"name","id","args","result","error"}` only | No `outputs` key exists |
| Service emitter | `ai_service.py:257-264` | Forwards `id,args,result,error` | `outputs` never forwarded |
| Step row stored | `assistant_view.py:822` | `row["outputs"] = payload.get("outputs", [])` → `[]` | Empty list |
| Render | `assistant_view.py:1290-1298` `build_ai_step_output(outputs=[])` | `parse_outputs_to_controls([])` → `[]` | Output area renders nothing |

---

## 2. Button bar today

`build_ai_step_output` (`ai_step_output.py:44-73`) builds `action_buttons`:

1. **"Open Terminal"** (`TERMINAL_ROUNDED`) — appended when
   `(tool_name == "_exec" and state in ("running","done")) or
   (tool_name == "read_terminal" and state in ("running","done"))` (line 46, precedence-bug
   form). Calls `on_open_terminal`.
2. **"Open Notebook"** (`DESCRIPTION_ROUNDED`) — appended when
   `tool_name == "read_notebook" and state in ("running","done")` (line 55). Calls
   `on_open_notebook`.
3. **"Copy"** (`COPY_ROUNDED`) — appended whenever `on_copy` is set (line 65-73).

Called from `assistant_view._render_assistant` (`assistant_view.py:1290-1298`):

```python
step_output = build_ai_step_output(
    tool_name=tool_name,
    outputs=row.get("outputs", []),
    state=row["state"],
    on_open_terminal=self._open_terminal_for_session,   # controller.open_terminal
    on_open_notebook=self._open_notebook_for_session,   # controller.open_notebook
    on_copy=lambda r=row: self._copy_step_output(r.get("outputs", [])),
)
```

The callbacks (`assistant_view.py:987-1005`) delegate to the controller:
`open_terminal(session_name)` sets `state.session_mode = "terminal"` and navigates to tab 2;
`open_notebook(session_name)` sets `state.session_mode = "notebook"` and navigates to tab 1
(`main.py:481-492`). The controller exposes `open_terminal`/`open_notebook` via
`ControllerMethods` (`src/state/controller_ctx.py:56-58`).

**Problem with today's bar:** the user wants actions = **[copy] + [open in terminal | open in
notebook]** (whichever applies), instead of copy/clear-output/terminal. Today there is no
"clear output" on AI step rows (clear-output exists only in the notebook cell,
`notebook_cell/__init__.py:343-342`), and the open action is chosen by a fragile tool-name/
state condition with no awareness of `session_mode` (`core/state.py:15`:
`session_mode: str = "notebook"  # "notebook", "terminal", "files"`).

---

## 3. Proposed design

### 3.1 Data flow fix (make `outputs` reach the step row)

The `outputs` list is produced by the tools but trapped inside the JSON-encoded `result`
string. Two complementary fixes:

**(A) Parse `result` JSON in `_on_tool_done`** (`assistant_view.py:806-824`) — the smallest
change. After `result = payload.get("result", "")`, try `json.loads(result)`; if it is a dict
with `"outputs"`, extract `outputs` and replace `result` with the `"text"` field (so the
outcome label stays clean):

```python
import json
result = payload.get("result", "")
outputs = []
try:
    parsed = json.loads(result)
    if isinstance(parsed, dict):
        outputs = list(parsed.get("outputs", []) or [])
        result = parsed.get("text", result)
except (ValueError, TypeError):
    pass
...
data = {
    ...
    "result": result,
    "outputs": outputs,
    ...
}
```

This handles `_exec` and `read_terminal` (both emit `json.dumps({"text":..., "outputs":...})`)
and gracefully degrades for tools that return plain strings (`read_notebook`, `read_file`,
`write_cells`, etc.), where `json.loads` fails and `outputs` stays `[]`.

**(B) (Alternative/cleaner) thread `outputs` through the step payload.** Have
`kani_backend.tool_specs` capture the tool's returned `outputs` if the body attaches them, or
have `ai_service._step_emitter` pass an `outputs` field. Given the tools currently embed
outputs inside `result`, option (A) is the minimal, local fix and is recommended.

### 3.2 Step row actions = [copy] + [open in terminal | open in notebook]

Replace the tool-name/state condition in `build_ai_step_output` with explicit, session-mode-
aware logic. The component needs to know whether to offer "Open Terminal" or "Open Notebook":

- `_exec` → open **notebook** if a notebook is open / `session_mode == "notebook"`, else open
  **terminal**.
- `read_terminal` → open **terminal**.
- `read_notebook` → open **notebook**.
- Other tools → no open action (copy only).

Since `build_ai_step_output` doesn't receive `session_mode`, pass it in (or pass the resolved
open-action). Proposed signature addition:

```python
def build_ai_step_output(tool_name, outputs, state, session_mode="notebook",
                         on_open_terminal=None, on_open_notebook=None, on_copy=None):
```

Action selection:

```python
def _open_action_for(tool_name, state, session_mode):
    if state not in ("running", "done"):
        return None
    if tool_name == "read_terminal":
        return "terminal"
    if tool_name == "read_notebook":
        return "notebook"
    if tool_name == "_exec":
        return "notebook" if session_mode == "notebook" else "terminal"
    return None
```

Render exactly two action slots in fixed order: **[Copy] + [Open Terminal | Open Notebook]**
(omit the open slot when not applicable). Drop any "clear output" from AI step rows (it's a
notebook-cell concept; the user explicitly wants copy + open only).

Also fix the precedence bug:
```python
if tool_name in ("_exec", "read_terminal") and state in ("running", "done"):
```

### 3.3 Output area uses the shared renderer (already wired, needs data)

`build_ai_step_output` already calls `parse_outputs_to_controls(outputs)` (`ai_step_output.py:
41`), which is the same function the notebook cell uses
(`notebook_cell/__init__.py:272-293`, `script_view.py:156`). Once `_on_tool_done` populates
`row["outputs"]`, the AI step output will render images/plots/html/json/markdown exactly like
the notebook. No change to `parse_outputs_to_controls` is needed for this audit (it was
recently upgraded to full MIME rendering per `dep-05-jupyter-libs.md#19` / audit-05 finding
#19).

For live streaming, `build_live_tool_output` (`ai_step_output.py:114-174`) renders plain text.
Optionally route live `tool_output` chunks into `row["outputs"]` as `{"type":"stream","text":...}`
entries so live output also goes through `parse_outputs_to_controls` (ANSI parsing, etc.) —
today live output bypasses it and renders raw `ft.Text` (`build_live_tool_output` line 149).

### 3.4 State needed to decide terminal-vs-notebook

- `state.session_mode` (`core/state.py:15`): `"notebook"` | `"terminal"` | `"files"` — tells
  which view is currently active, used to decide `_exec`'s open target.
- `tool_name` (`row["name"]`): `_exec` / `read_terminal` / `read_notebook` / other.
- `row["state"]`: `"running"` | `"done"` | `"error"` — open actions only in running/done (per
  audit-01 #12, do not show open button on error).

The open-action callbacks already exist on `ChatSession` (`_open_terminal_for_session`,
`_open_notebook_for_session`, `assistant_view.py:987-1005`) and are wired to the controller
(`main.py:481-492`, `controller_ctx.py:56-58`).

---

## 4. Findings table

| # | Severity | Location | Finding | Fix |
|---|----------|----------|---------|-----|
| 1 | **critical** | `src/services/ai_tools.py:194-199` (`_exec`) and `:276-280` (`read_terminal`) | Rich `outputs` list is JSON-encoded into the `result` string (`json.dumps({"text":..., "outputs":...})`) instead of being a separate payload field. Nothing parses it back out, so the step row never receives outputs → empty output area with only a copy button. | In `ChatSession._on_tool_done` (`assistant_view.py:806-824`), `json.loads(result)`; if dict with `"outputs"`, set `row["outputs"]` and use `"text"` as the clean `result`. Gracefully degrade for plain-string tools. |
| 2 | **critical** | `src/services/kani_backend.py:143-149` + docstring `:130` | Step payload schema is `{"name","id","args","result","error"}` only — no `outputs` key, so `payload.get("outputs", [])` is always `[]` in `_on_tool_done`. | Either thread `outputs` through `tool_specs`/`_step_emitter`, or rely on fix #1 (parse `result`). |
| 3 | **high** | `src/screens/assistant_view.py:1290-1298` | `build_ai_step_output(outputs=row.get("outputs", []))` receives `[]` → `parse_outputs_to_controls([])` → `[]` → empty output area. `row["result"]` also holds the raw JSON string, leaking garbled JSON into the step-row outcome label (`assistant_view.py:1275-1279`). | Populate `outputs` (fix #1) and store cleaned `result` text so the label is short and user-legible. |
| 4 | **medium** | `src/components/ai_step_output.py:46` | Operator-precedence condition `(tool_name == "_exec" and ...) or (tool_name == "read_terminal" and ...)` — fragile, hard to read (audit-01 #12). Does not account for `session_mode` to choose terminal vs notebook. | Rewrite as `tool_name in ("_exec", "read_terminal") and state in (...)`; add session-mode-aware action selection (`_exec` → notebook if `session_mode=="notebook"` else terminal). |
| 5 | **medium** | `src/components/ai_step_output.py:44-73` | Action bar does not match the requested "[copy] + [open terminal | open notebook]" shape; no session-mode awareness; no clear way to pick the right open target. | Render fixed actions: [Copy] + one open action chosen by tool/session_state; omit open when not applicable (esp. not on `error`). |
| 6 | **low** | `src/components/ai_step_output.py:114-174` (`build_live_tool_output`) | Live streaming output renders raw `ft.Text`, bypassing `parse_outputs_to_controls` (no ANSI/image/MIME rendering). | Optionally feed live `tool_output` chunks into `row["outputs"]` as stream entries so live output also uses the shared renderer. |
| 7 | **info** | `docs/audit-01-ai-assistant.md#12` | The precedence bug is real but cosmetic; the functional impact is superseded by findings #4/#5 (missing session-mode awareness). | Addressed by #4/#5. |

---

## 5. Exact files / functions to change

| File | Function / lines | Change |
|------|------------------|--------|
| `src/screens/assistant_view.py` | `ChatSession._on_tool_done` (lines 806-824) | Parse `result` as JSON; extract `outputs` into `data["outputs"]`; use `parsed["text"]` as cleaned `result`. Add `import json`. |
| `src/screens/assistant_view.py` | `ChatSession._render_assistant` (lines 1273-1298) | Pass `session_mode=self.state.session_mode` to `build_ai_step_output`; ensure `outputs=row.get("outputs", [])` now populated; keep label short from cleaned `result`. |
| `src/components/ai_step_output.py` | `build_ai_step_output` (lines 19-111, esp. 44-73) | Add `session_mode` param; replace precedence condition with `tool_name in ("_exec","read_terminal") and state in (...)`; select open action by tool + `session_mode`; render fixed [Copy] + [Open Terminal \| Open Notebook] (omit open on `error`/N/A); fix `read_terminal`+`error` edge. |
| `src/components/ai_step_output.py` | `build_live_tool_output` (lines 114-174) | Optional: route live output through `parse_outputs_to_controls` for ANSI/MIME rendering parity. |
| `src/services/kani_backend.py` | `tool_specs` (lines 143-179, docstring line 130) | Optional: add `outputs` to the step payload schema so it's not reliant on parsing `result`. |

### Verification

- `ls docs/audit-09-ai-output-rendering.md` — confirm the report file exists at the exact path.
- After the fix, `_exec`/`read_terminal` steps with rich outputs should render images/plots/
  html/json via `parse_outputs_to_controls` (same as notebook cells), and the step row should
  show [Copy] + one open action (terminal or notebook depending on tool / `session_mode`).

*Note: This is a read-only audit. No source files were modified; only this report was written.*
