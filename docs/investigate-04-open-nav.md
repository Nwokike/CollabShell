# Investigate-04 — "Open Notebook" / "Open Terminal" navigation from AI step rows

READ-ONLY investigation of CollabShell @ 0dfa74e (v2.2.0, build 15). Issue: pressing
"Open Notebook" (or "Open Terminal") on an AI step row takes the user to the NOTEBOOKS
part of the HOME page (the session list), not the session's notebook screen, and shows no
output. Every AI code run (`_exec`) shows "Open Notebook", never "Open Terminal".

## 1. Current nav trace (routes, file:line)

All routes are applied in one place, `_apply_route`, defined in `src/main.py:363-410`:

- `_TAB_ROUTES` (`main.py:347-354`): `/`→0, `/home`→0, `/notebooks_tab`→1,
  `/terminals_tab`→2, `/files_tab`→3, `/settings`→4.
- `_apply_route` (`main.py:363-410`):
  - path in `_TAB_ROUTES` → `state.active_subview = ""`, `state.active_session_name = ""`,
    `state.current_tab = idx` (`main.py:374-378`). NOTE: the tab routes CLEAR the active
    session and subview.
  - `/session?session=<name>[&tab=terminal]` → `active_session_name = name`,
    `session_mode = "terminal" if tab==terminal else "notebook"`, `active_subview = "session"`
    (`main.py:379-387`).
  - `/terminal?session=<name>` → `session_mode = "terminal"`, `active_subview = "session"`
    (`main.py:388-394`). `/files?session=<name>` → `session_mode = "files"` (`main.py:395-401`).
- `_navigate(route)` (`main.py:412-419`) = `_apply_route(route)` + `page.route = route`.

Controller closures (`src/main.py`):

- `_navigate_tab(idx)` (`main.py:433-435`) → `_navigate(_TAB_ROUTE_NAMES[idx])` → a TAB
  route (`/home`, `/notebooks_tab`, ...). Pure home-dashboard tab switch.
- `_open_session(name, mode)` (`main.py:437-444`) → `/files?session=…`,
  `/terminal?session=…`, else `/session?session=…` — the SESSION screen routes.
- `_open_terminal(session_name)` (`main.py:495-500`): sets `state.active_session_name` and
  `state.session_mode = "terminal"`, then calls `_navigate_tab(2)` → `/terminals_tab`.
- `_open_notebook(session_name)` (`main.py:502-506`): sets state, then
  `_navigate_tab(1)` → `/notebooks_tab`.
- Wired into `ControllerMethods` as `open_terminal=_open_terminal, open_notebook=_open_notebook`
  (`main.py:542-543`); fields declared at `src/state/controller_ctx.py:55-58`
  (`reveal_cell` at :53-54, `open_session` at :30).

What renders (`src/app_shell.py`):

- `state.active_subview == "session" and state.active_session_name` → `SessionScreen(
  session_name, mode=state.session_mode, …)` (`app_shell.py:444-506`). SessionScreen has an
  internal notebook/terminal tab switcher, initialized from `mode`
  (`src/screens/session/__init__.py:25-33`: `0 if mode == "notebook" else 1`).
- Otherwise the dashboard renders by `state.current_tab`: tab 1 →
  `SessionSelectorTab(mode="notebook")` (`app_shell.py:644-647`), tab 2 →
  `SessionSelectorTab(mode="terminal")` (`app_shell.py:648-651`) — the session LIST on the
  home tabs. Tapping a card there correctly calls `controller.open_session(name, mode)`
  (`src/screens/session_selector.py:23-24`; also `src/screens/home/__init__.py:63`).

Assistant side (`src/screens/assistant_view.py`):

- Step rows are built at `assistant_view.py:1322-1381`; each row's output panel calls
  `build_ai_step_output(..., session_mode=state.session_mode, on_open_terminal=
  lambda r=row: self._open_terminal_for_session(r), on_open_notebook=
  lambda r=row: self._open_notebook_for_session(r))` (`assistant_view.py:1371-1380`).
- `_open_terminal_for_session(row)` (`assistant_view.py:1015-1033`): `self.close()`
  (minimize chat, 2.2.0 addition), then `controller.open_terminal(state.active_session_name)`.
- `_open_notebook_for_session(row)` (`assistant_view.py:1035-1054`): `self.close()`, then
  `controller.open_notebook(...)`, then if the row has `refs`, `self._reveal_cell(refs[0])`.
- `_reveal_cell(cell_id)` (`assistant_view.py:1001-1013`) → `controller.reveal_cell(session, cell_id)`
  → `main.py:486-493` → `notebook_view.reveal_cell(session_name, cell_id)`.
- `_cell_refs(step)` (`assistant_view.py:254-267`) parses the `"Cells: <id>, …"` tail
  (`_CELL_REF_PREFIX`, :177) that only the `write_cells` tool emits
  (`src/services/ai_tools.py:485`); rows get `"refs"` at `assistant_view.py:847`.

Open-action target rule today (`src/components/ai_step_output.py:34-75`,
`_open_action_buttons`): `read_terminal` → terminal; `_exec`, `read_notebook`,
`write_cells`, `install_package` → notebook ALWAYS; other openable tools → `session_mode`
if in (notebook, terminal) else notebook (:47-54). Hence every code run shows
"Open Notebook" only.

## 2. Why open_notebook lands on the HOME notebooks tab

`_open_notebook(name)` (`main.py:502-506`) sets `state.active_session_name = name` and
`state.session_mode = "notebook"`, then calls `_navigate_tab(1)` → `_navigate("/notebooks_tab")`
→ `_apply_route("/notebooks_tab")` hits the `_TAB_ROUTES` branch (`main.py:374-378`) which
sets `active_subview = ""` and `active_session_name = ""` — wiping the two values set one
line earlier — and sets `current_tab = 1`. In `AppShell`, `active_subview` is no longer
`"session"`, so the session subview branch (`app_shell.py:444`) is skipped and the
dashboard branch renders `current_tab == 1` → `SessionSelectorTab(mode="notebook")`
(`app_shell.py:644-647`): the NOTEBOOKS session list on Home. No SessionScreen is mounted,
so no notebook (and no output) is shown. Same mechanism for `_open_terminal` → tab 2
(Terminals list). The bug exists identically on `backup/pre-squash-v2.1.2`
(pre-squash `main.py:463-474`).

Additionally, since no session screen mounts, `notebook_view._SESSION_BRIDGES` has no entry
for the session (published on NotebookView render, `notebook_view.py:1205-1235`; popped on
unmount, :421), so the `reveal_cell` call in `_open_notebook_for_session` always fails and
`main.py:491-493` shows the warning "That cell is no longer in the notebook."

## 3. Correct fix (exact functions/routes)

`open_notebook`/`open_terminal` must use the session routes, i.e. delegate to `_open_session`:

```python
# src/main.py, replace _open_terminal (main.py:495-500) and _open_notebook (main.py:502-506):
def _open_terminal(session_name: str):
    _open_session(session_name, "terminal")   # → _navigate("/terminal?session=<name>")

def _open_notebook(session_name: str):
    _open_session(session_name, "notebook")   # → _navigate("/session?session=<name>")
```

`_open_session(name, mode)` (`main.py:437-444`) already URL-quotes and produces
`/terminal?session=<encoded>` / `/session?session=<encoded>`; `_apply_route` then sets
`active_subview = "session"`, `active_session_name`, `session_mode`
(`main.py:379-394`), and `AppShell` renders `SessionScreen(session_name, mode=session_mode)`
(`app_shell.py:494-506`) — the session's notebook screen (or terminal tab). This matches how
the rest of the app opens sessions (`session_selector.py:24`, `home/__init__.py:63`).
Equivalent alternative: `_navigate(f"/session?session={quote(name)}&tab=terminal")` —
`/session` with `tab=terminal` sets terminal mode (`main.py:383-385`).

Sequencing caveat in `_open_notebook_for_session` (`assistant_view.py:1050-1054`): it calls
`_reveal_cell` synchronously right after the navigate handler. Bridges only exist once the
NotebookView has rendered, so the reveal succeeds only when the session screen was already
mounted (assistant opened from inside the session). When opening from Home, the reveal must
be deferred until the view mounts (e.g. `page.run_task` retry, or a pending-reveal hook in
NotebookView's mount), otherwise `main.py:491-493` fires the "no longer in the notebook"
warning.

## 4. Open-target rule decision

Current rule (`ai_step_output.py:47-54`) is tool-based and hard-codes `_exec` → notebook.
Owner wants the button to match where the work lives. Proposed rule (combines the issue's
proposal with `docs/audit-09-ai-output-rendering.md:217-229`):

- `read_terminal` → **terminal** always (it reads the PTY scrollback,
  `ai_tools.py:313` → `terminal_panel.read_terminal_scrollback`, `terminal_panel.py:50-66`).
- `write_cells`, `read_notebook` → **notebook** always (they write/read cells;
  `write_cells` emits the `Cells:` refs that drive the reveal).
- `_exec`, `install_package` (kernel work) → **`session_mode` decides**: the tab the session
  is currently on (`notebook`/`terminal`), falling back to notebook — exactly what
  `assistant_view.py:1375` already passes in. This makes code runs show "Open Terminal" when
  the session is on the terminal tab and "Open Notebook" when on the notebook tab.
- `read_file`, `list_files`, `upload_file` → `session_mode` fallback as today, or no open
  action (copy only), per audit-09.

Note the rule flipped between releases: pre-squash `ai_step_output.py:46-63` sent `_exec` and
`read_terminal` to "Open Terminal" and `read_notebook` to "Open Notebook"; 2.2.0 made `_exec`
notebook-always. Also note `session_mode` is stale when the assistant is opened from Home
(tab routes clear `active_session_name` but not `session_mode`, `main.py:374-378`), so a
fallback of `notebook` is required.

## 5. The output-in-notebook question

What happens to `_exec` output today: `ai_tools._exec` (`src/services/ai_tools.py:184-244`)
calls `services.colab.exec_code(...)` (:221-229), which is `exec_code_impl`
(`src/services/colab/execution.py:69+`) driving `runtime.execute_code(...)` (:356) — the
Jupyter kernel API, NOT a notebook cell and NOT the PTY. The output is streamed only into the
chat step row (`on_tool_output` → `live_output`, plus the `{"text","outputs"}` JSON envelope
returned at :237-241 and parsed onto the row at `assistant_view.py:822-851`). So the code the
AI ran and its output exist ONLY in the (minimizable) chat; `state.exec_output_lines`
(`core/state.py:25`) is vestigial — written nowhere. Contrast: a user-run cell
(`notebook_view._run_cell`, `notebook_view.py:451-481`) appends every output into the cell via
`_append_output`. The only AI path that writes into the notebook is `write_cells`
(`ai_tools.py:455-488` → `notebook_view.write_cells_to_active_tab`, `notebook_view.py:46-86`),
whose `"Cells: <ids>"` tail becomes the row's `refs` and is revealed by
`_open_notebook_for_session`.

Pre-squash branch: the open handlers were plain `controller.open_*` calls with NO minimize and
NO reveal (`backup/pre-squash-v2.1.2` `assistant_view.py:987-1006`), and pre-squash `main.py`
called `open_assistant(page, state, services)` without `methods`, so `controller=None` and all
open/reveal actions silently no-oped. 2.2.0 added `self.close()` (minimize, keeps a running
turn alive, `assistant_view.py:614-631`) before navigating and the refs reveal
(diff `backup/pre-squash-v2.1.2..main` on `assistant_view.py`; `main.py` now passes `methods`,
`main.py:471-479`).

DDGS equivalent (`/home/maikel/Desktop/kiri-apps/DDGS`): a step/card's "Open N results"
button (`chat_screen.py:2364`) calls `_open_results` (`chat_screen.py:2439-2444`), which does
`ctrl.open_assistant_results(results, kind)` and THEN `self.close()` (minimize).
`open_assistant_results` (`app_controller.py:1033-1051`) loads the assistant's results INTO
the live Results screen state (`state.search_progress`/`last_results`) — i.e. the data is
handed to the real surface and shown there, not just navigated to. That is the "open-in-results
model" the 2.2.0 docstring cites (`assistant_view.py:1036-1038`).

Recommendation: for an `_exec` step, "Open Notebook" should (after the §3 nav fix)
(1) navigate to `/session?session=<name>` in notebook mode, AND (2) when a notebook view is
mounted for that session (bridges present), insert a code cell with `origin="assistant"`,
`tool_call_id=<step id>`, `source=<the code arg>`, `outputs=<the step's outputs>` into the
active tab — extending `write_cells_to_active_tab` to accept `outputs` (today it builds
`CellData` from only type/source/origin/tool_call_id, `notebook_view.py:72-86`) — then reveal
it via the existing `reveal_cell` bridge, mirroring the `write_cells` refs path; (3) when no
notebook tab is open (bridges `None`, e.g. assistant opened from Home or a script tab is
active), just open the session notebook screen and leave the output in the minimized chat
(FAB "Back to Assistant" restores it). Do not write a cell when the resolved target is
terminal. This matches the owner's expectation ("see the code the AI ran and the output in a
notebook") and the DDGS hand-the-data-to-the-live-surface pattern. The simpler alternative —
Open Notebook as pure navigation to the session's notebook screen — fixes where you land but
NOT the "no output" complaint, since no cell ever contains the `_exec` output.

Related 2.2.0 interaction: `_open_*_for_session` call `self.close()` before navigating
(`assistant_view.py:1024, 1040`) so the tab switch is not hidden under the chat view;
`close()` minimizes (pops the chat view, sets `assistant_minimized=True`, keeps the session and
any running turn; `assistant_view.py:614-631`), and `_on_view_pop` (`main.py:919-929`) minimizes
on BACK when the chat is the top view. Side finding: `main.py:930-934` (the
`active_subview`/views-pop branch in `_on_view_pop`) is dead code after the unconditional
`return` at :928.

## 6. Findings table

| # | File:line | Finding | Severity |
|---|-----------|---------|----------|
| 1 | `src/main.py:495-506` | `_open_terminal`/`_open_notebook` call `_navigate_tab(2/1)` instead of the session routes; the tab-route branch of `_apply_route` (`main.py:374-378`) wipes the just-set `active_session_name`/`active_subview` → lands on Home Notebooks/Terminals list (`app_shell.py:644-651`), not the session screen. Bug pre-exists on `backup/pre-squash-v2.1.2` (`main.py:463-474`). | HIGH (the reported bug) |
| 2 | `src/main.py:437-444` vs `:433-435` | `_open_session(name, mode)` is the correct route producer (`/session`, `/terminal`, `/files` ?session=); used by `session_selector.py:24` and `home/__init__.py:63`. Fix: delegate `open_notebook`/`open_terminal` to it. | HIGH (fix location) |
| 3 | `src/components/ai_step_output.py:47-54` | Open-action target is tool-based: `_exec`→notebook always, so "Open Terminal" never appears on code runs; pre-squash had `_exec`→terminal (rule flipped in 2.2.0). Owner rule: `session_mode` decides for kernel tools, `read_terminal` always terminal. | MEDIUM |
| 4 | `src/screens/assistant_view.py:1371-1380` | Step row passes `session_mode=state.session_mode` and both handlers; `state.session_mode` can be stale when the chat was opened from Home (tab routes don't reset it). | LOW |
| 5 | `src/services/ai_tools.py:184-244` + `src/services/colab/execution.py:69-356` | `_exec` runs via kernel `execute_code`, not a cell/PTY; its code+output land only in the chat row (`assistant_view.py:822-851`). No notebook cell ever contains it → "no output" after Open Notebook even once nav is fixed. `state.exec_output_lines` (`core/state.py:25`) is write-never. | HIGH (drives §5 decision) |
| 6 | `src/screens/session/notebook_view.py:46-86, 89-115, 1205-1235, 421` | `write_cells_to_active_tab` (no `outputs` param) and `reveal_cell` work only while the session's NotebookView is mounted (bridges). `_open_notebook_for_session`'s sync reveal (`assistant_view.py:1050-1054`) races the mount when coming from Home → warning toast at `main.py:491-493`. | MEDIUM |
| 7 | `src/screens/assistant_view.py:1015-1054` + `main.py:471-479` | 2.2.0 added `self.close()` minimize-before-navigate and the refs reveal (diff vs `backup/pre-squash-v2.1.2`, where `controller=None` made these no-op). Minimize keeps running turns alive (`close()`, `:614-631`); BACK handling at `main.py:919-929`. | INFO (works as intended) |
| 8 | `src/main.py:928-934` | Dead code: unconditional `return` at :928 makes the subview-close branch below unreachable. | LOW |
| 9 | DDGS `chat_screen.py:2364, 2439-2444`; `app_controller.py:1033-1051` | Reference pattern: "Open N results" hands the data to the live Results screen (`open_assistant_results`) then minimizes the chat — the model for §5's write-cell-and-reveal. | INFO |
| 10 | `docs/audit-09-ai-output-rendering.md:217-229` | Prior audit already proposed the session_mode-aware open rule (`_exec` → notebook if `session_mode=="notebook"` else terminal; `read_terminal`→terminal; `read_notebook`→notebook; others→none). | INFO |
