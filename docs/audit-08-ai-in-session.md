# Audit 08 — AI in Session (Terminal + Notebook)

**Repo:** /home/maikel/Desktop/kiri-apps/ColabShell  
**Baseline:** HEAD (76a9d4b)  
**Scope:** AI implementation inside the TERMINAL and inside the NOTEBOOK  
**Mode:** Read-only source inspection; no files modified.

---

## Verdict

**Terminal: NOT PERFECT.** The terminal AI surface is effectively dead. `read_terminal_scrollback()` (terminal_panel.py:50) delegates to `_read_scrollback()` (terminal_panel.py:684), which calls `(ps.terminals or {}).values()` — but `ps.terminals` is a `list` (`self.terminals: list = []` at line 136), not a dict. `.values()` raises `AttributeError`, which is caught by the try/except at lines 62-66 and returns `""`. Result: the terminal "Explain" AI action always sees an empty scrollback and replies "Nothing in the terminal to explain yet," and the `read_terminal` AI tool always returns "(terminal is empty)". Neither terminal AI feature can see any terminal output. The end-to-end path (button → scrollback read → AI ask → dialog) is broken at the scrollback-read step.

**Notebook: NOT PERFECT.** The in-cell AI actions (Explain / Fix error / Suggest next / Suggest hardware) are wired end-to-end and generally work — answers are inserted as cells, errors degrade to notices, credits are metered. However, `read_notebook` drops rich-output text (`text/plain` nested under `data`), `write_cells` can silently write into script tabs where nothing is rendered, `_cell_has_plot` works but output rendering misses most MIME types, and the `fix` action inserts unvalidated code that may contain model hedging.

---

## Findings Table

| # | Severity | Location | Finding | Fix |
|---|----------|----------|---------|-----|
| 1 | **Critical** | `src/screens/session/terminal_panel.py:684-695` | `_read_scrollback` calls `.values()` on `ps.terminals`, which is a `list` (`self.terminals: list = []` at line 136), not a dict. `AttributeError` is caught by `read_terminal_scrollback` (lines 62-66) and returns `""`. Terminal explain always reports "Nothing in the terminal to explain yet"; `read_terminal` tool always returns "(terminal is empty)". Both terminal AI features are dead. | Change iteration to `for entry in ps.terminals:` (it is already a list of TerminalEntry objects), or make `terminals` a dict keyed by id. |
| 2 | **Critical** | `src/screens/session/terminal_panel.py:684-695` | `_read_scrollback` concatenates all tabs' scrollback indiscriminately (oldest tab first, newest last), mixing unrelated output across multiple terminals. Secondary to #1 (already broken), but a design flaw once fixed. | Scope scrollback to the active tab only, or prefix each tab's output with its tab id. |
| 3 | **High** | `src/services/ai_tools.py:244-248` | `read_notebook` renders cell outputs via `o.get("text", "")`. For `display_data`/`execute_result` outputs, text lives under `data["text/plain"]`, not at top level `text`. Rich-output text (plot captions, dataframe `text/plain`, HTML) is missing from `read_notebook`. Only stream outputs surface text. | In `read_notebook`, fall back to `o.get("data", {}).get("text/plain", "")` when `o.get("text")` is empty. |
| 4 | **Medium** | `src/screens/session/notebook_view.py:46-80` | `write_cells_to_active_tab` (used by the `write_cells` AI tool) inserts cells into the active tab without checking whether it is a script tab. Script tabs have `"cells": []`; cells are added to the data model but never rendered. The tool reports success but nothing appears. `read_notebook` (lines 226-234) correctly guards against script tabs; `write_cells` does not. | In `write_cells_to_active_tab`, check `active_tab.get("view") == "script"` and return a "cannot write to script tab" message, mirroring `read_notebook`. |
| 5 | **Medium** | `src/services/ai_tools.py:53-68` + `src/components/notebook_cell/output.py:7` | `_cell_has_plot` (ai_tools) includes `image/gif` in `_PLOT_MIMES`; `output.py`'s `_IMAGE_MIMES` does not. Minor inconsistency, harmless — plot detection itself works correctly for standard nbformat mime bundles. | Align mime sets (add `image/gif` to `output.py` or remove from `ai_tools`). Cosmetic only. |
| 6 | **Medium** | `src/services/ai_tools.py:128-129` | `_exec` docstring claims `clear_output()` "is not supported here and will silently do nothing." `_to_cell_output` in execution.py does not convert clear_output kernel messages, so the claim is accurate for `_exec`. However `output.py:56-58` renders clear_output as an empty container, and `_import_ipynb` does not handle clear_output msg_types (dep-05 #28) — clear_output handling is dead code throughout. Docstring and renderer contradict each other. | Either implement clear_output in `_to_cell_output` and the import path, or remove the clear_output branch from `output.py` and update the docstring to say clear_output is dropped. |
| 7 | **Low** | `src/services/cell_ai.py:99-103, 143-166` | The `fix` action tells the model to reply with only a code block, but `extract_code()` falls back to raw text when no fence is found. A hedging model produces a cell containing explanation + code, which fails on execution. No Python validation (`compile`) before insertion. | After `extract_code()`, validate with `compile(body, "<fix>", "exec")`; if invalid, return empty so the caller shows "The Assistant returned nothing usable." |
| 8 | **Low** | `src/services/cell_ai.py:76-87` | `_output_digest` extracts `getattr(out, "text", None)` / `out.get("text")`. For `display_data`/`execute_result` outputs the text is under `data["text/plain"]`. Fix-error may not see the full error text if it arrived as a rich output. | Fall back to `o.get("data", {}).get("text/plain")` in `_output_digest`. |
| 9 | **Info** | `src/services/ai_tools.py:180-193` | `_exec` has keepalive + re-sync retry for idle sessions (catches 404/401/"not found"/"could not reach", re-syncs via `list_sessions`, retries once). This works for `_exec` only — `read_notebook`, `read_terminal`, `read_file`, `list_files`, `install_package` have no retry and will fail on idle-pruned sessions. | Apply the same re-sync + retry pattern to the other session-bound tools, or document that only `_exec` heals idle sessions. |
| 10 | **Info** | `src/screens/session/terminal_panel.py:675, 714-773` | Terminal "explain" action IS wired (`on_ai_explain` → `term_actions["explain"]` → `_explain_terminal`), and error paths (OutOfCredits, CellAIDisabled, generic Exception) all degrade to snack notices. No unhandled exceptions escape. But it is moot because of #1. | Fix #1; then terminal explain works end-to-end. |
| 11 | **Info** | `src/screens/session/notebook_view.py:527-604, 1180-1187` | Notebook AI actions (`ask_ai_active`, `suggest_hardware`) are wired end-to-end. `_run_cell_ai` catches OutOfCredits, CellAIDisabled, and generic exceptions → notices. `_insert_ai_answer` rejects empty answers. `suggest_hardware` appends markdown at end. All work. | No fix needed. |

---

## End-to-End Assessment per AI Action

| Action | Works end-to-end? | Notes |
|--------|-------------------|-------|
| Terminal "Explain" | **NO** | Blocked by Finding #1 (scrollback always empty). Button is wired but reads nothing. |
| `read_terminal` tool | **NO** | Same Finding #1 — always returns "(terminal is empty)". |
| `_exec` tool | **YES** | Streams output via `on_tool_output`, clips to 12000 chars, attaches outputs JSON, heals idle sessions via re-sync retry. Error path returns "Execution failed: …". |
| `read_notebook` tool | **PARTIAL** | Reads cells and source correctly, but drops `data["text/plain"]` rich output (Finding #3). Marks plots with "[plot]" correctly via `_cell_has_plot`. |
| `write_cells` tool | **PARTIAL** | Writes cells but silently fails to render on script tabs (Finding #4). |
| Notebook "Explain" | **YES** | Inserts markdown answer cell under target cell. Handles credits/OOM as notices. |
| Notebook "Fix error" | **PARTIAL** | Works but inserts unvalidated code that may include model hedging (Finding #7). Error digest may miss rich-output text (Finding #8). |
| Notebook "Suggest next" | **YES** | Inserts code cell under target cell. |
| Notebook "Suggest hardware" | **YES** | Appends markdown recommendation cell at end. |
| `install_package` | **YES** | Delegates to `install_packages_impl`. No idle-session retry (Finding #9). |
| `list_variables` | **YES** | Runs `_exec` with introspection code. Inherits `_exec`'s retry. |
| `read_file` / `list_files` / `upload_file` | **YES** | VM file operations. No idle-session retry (Finding #9). |
| `list_notebook_tabs` | **YES** | Reads bridges. Returns "(no tabs)" when none open. |
| `get_usage` / `get_log` | **YES** | Read-only. |

---

## Cross-Check: lm-router chat tools

`/home/maikel/Desktop/kiri-apps/lm-router/src/services/router_tools.py` exposes three read-only router diagnostic tools: `gateway_status`, `list_models`, `probe_model`. These follow the same "docstring is the model-visible instruction" pattern as `ai_tools.py` (docstring IS the spec, JSON schema derived from signature via `AIParam`). They are router/domain tools (gateway health, catalog, single-model probe) — different domain from ColabShell's session tools (`_exec`, `read_notebook`, `read_terminal`, etc.), no functional overlap, no shared bugs. lm-router tools use `auto_retry=False` and explicit `auto_truncate`; ColabShell's `ai_tools.tool_specs` derives truncation from `TOOL_OUTPUT_CAP` (12000) via `kani_backend.build_functions` — equivalent contract.

---

## Cross-Check: DDGS ai_overview / ai_summary

From `docs/ref-01-ddgs-patterns.md` §5.4-5.5: DDGS has passive AI cards — `ai_overview` (collapsed markdown + "Read full report", honest error states for credits exhausted / midstream loss / unavailable) and `ai_summary` (streams tokens via `on_token`, throttled to 0.2s, terminal actions only — "Ask Assistant about this page" or "Get credits", no begin button). ColabShell has **no equivalent passive AI surface** in either terminal or notebook. The terminal explain is an active dialog (button → answer in `AlertDialog`), and in-cell AI inserts editable cells. Neither offers a passive, collapsed-by-default overview/summary card. This is a missing feature, not a bug — ColabShell's AI is explicitly on-demand and tool-free per `cell_ai.py` docstring ("deliberately tool-free: the whole notebook is passed in the prompt and the model answers in one step").

---

## Session Live-Read / Output Streaming / Error Paths (detail)

**Session live-read:** `ai_tools._live_session()` (lines 95-105) reads `state.active_session_name` live rather than capturing at build time — this fixes the historical "wrong session captured" bug. `read_notebook`, `read_terminal`, `write_cells`, `list_notebook_tabs` all go through per-session bridges (`_SESSION_BRIDGES`, published by `notebook_view.py:1193` and `terminal_panel.py:777`). These require the notebook/terminal tab to be open in the UI; they return honest "not open" messages otherwise. No wrong-session capture remains.

**Output streaming:** Only `_exec` streams (via `on_tool_output` callback, lines 147-148, plumbed through `kani_backend.tool_specs` lines 153-158). `read_terminal` and `read_notebook` return complete results at once — acceptable for read-only tools.

**Error paths:** All AI tools catch exceptions and return strings (never raise into the agent loop). `_exec` has the idle-session re-sync retry (lines 178-193). In-cell AI (`_run_cell_ai`, notebook_view.py:527) degrades all failures to snack notices. Terminal explain (`_explain_terminal`, terminal_panel.py:714) degrades to snack notices. No unhandled exceptions escape any AI action.

---

## Files Checked (Read-Only)

- `src/services/ai_tools.py` (entire — 15 tools, `_exec`, guards, error returns)
- `src/services/cell_ai.py` (in-cell AI service)
- `src/services/ai_quick.py` (shared metered ask engine)
- `src/services/kani_backend.py` (tool specs, step rows, `_exec` wiring)
- `src/screens/session/terminal_panel.py` (terminal AI surface, scrollback, explain action)
- `src/screens/session/__init__.py` (SessionScreen AI actions in FAB overflow menu)
- `src/screens/session/notebook_view.py` (bridges, `ask_ai_active`, `suggest_hardware`, `_run_cell_ai`, `write_cells_to_active_tab`)
- `src/components/notebook_cell/actions.py` (AI cell menu, `AI_CELL_ACTIONS`)
- `src/components/notebook_cell/output.py` (output rendering, MIME handling)
- `/home/maikel/Desktop/kiri-apps/lm-router/src/services/router_tools.py` (cross-check)
- `docs/audit-01-ai-assistant.md`, `docs/audit-04-colab.md`, `docs/dep-05-jupyter-libs.md`, `docs/ref-01-ddgs-patterns.md` (cross-check docs)
