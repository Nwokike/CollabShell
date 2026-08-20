# Colab Shell — Full UX Repair + flet_terminal Upgrade

Everything below verified against `.venv` Flet 0.86.5 source, the legacy Colab-ORIGINAL, SpanInsight, and KTV Player. auth_gcp and Drive mount were audited and are **genuinely functional end-to-end** (real `google.colab` code executed on the VM kernel via colab_cli `ColabRuntime` with real OAuth interception) — they stay, just relocated.

## Phase 1 — Critical bugs (things that are broken right now)

**1. Invisible notebook output** (`components/notebook_cell/__init__.py`)
Root cause verified: `_get_output_controls()` returns `cache["controls"]` — the *same list object* every render, mutated in place via `.extend()`. The previous frozen render's ListView already references that list, so when streaming appends to it, old==new in Flet's reconciler → nothing paints. Text exists (copy works), and remounting (leave + return) builds a fresh cache → visible. Fix: keep the incremental parse cache but **return a shallow copy** (`list(cache["controls"])`) so the previously-rendered list is never mutated. Also fix `calc_height` (lines 235-239): it reads `ctrl.value` but the ANSI parser returns `ft.Text(spans=..., value=None)` — count lines from `ctrl.spans` text instead.

**2. Notifications black-on-black / white-on-white** (`core/notifications.py:37`)
Verified: with no flag, `bgcolor=None` → SnackBar falls back to theme `inverseSurface` (dark in light mode) while text uses `ON_SURFACE` (also dark) → invisible. Fix: always set an explicit bgcolor (info → `AppColors.DARK_BG`) with `ft.Colors.WHITE` text in every mode; keep error/warning/success colors.

**3. Files: can't navigate above /content** (`screens/files/components.py` + legacy parity)
`build_breadcrumbs` hardcodes the "/" crumb → `/content`; there is no up button. The service already supports any path — `ls_impl` normalizes `/` → root (`files_ops.py:24-26`). Legacy had both a true-root crumb and an `ARROW_UPWARD` go-up button. Fix: root crumb navigates to `"/"`, render crumbs for every path segment, and add a go-up `IconButton` (`posixpath.dirname`, floor at `/`) to both the FilesScreen toolbar and the Manage Files modal.

**4. Files: "Select items" does nothing** (`screens/files/__init__.py:176`)
The selection action bar is gated on `selection_mode AND selected` — after clicking Select Items the selection is empty, so nothing visible happens. Fix: gate on `selection_mode` alone; show the selection bar immediately (count + Download/Delete enabled once ≥1 selected, plus Cancel). Items already render check icons in selection mode. Add the same Select toggle to the Manage Files modal (currently tap-only).

**5. Upload FAB is a bare orange circle** (`screens/files/__init__.py:351-372`)
`content=ft.Row([icon, text])` collapses to a circular FAB in 0.86.x. Legacy used the extended-FAB API. Fix: `ft.FloatingActionButton(content="Upload", icon=ft.Icons.UPLOAD_FILE_ROUNDED)` (verified props: `content: StrOrControl`, `icon`). Also upgrade the upload dialog: upload icon + filename title + size, instead of a naked progress bar.

**6. Markdown auto-render** (`components/notebook_cell/__init__.py:121`)
`on_blur` exists but only flips `is_editing`. Fix: on blur, commit the latest source first, then render (`_commit_source(e.control.value or ""); cell.is_editing = False`) — so tapping into another cell renders the markdown without needing Done (Done button stays as an explicit affordance).

## Phase 2 — Session screen UX

**7. Compact tab switcher in the header** (`screens/session/__init__.py`)
Delete the full-row `ft.SegmentedButton`. Build a compact two-segment pill (Notebook | Terminal) copied from SpanInsight's `build_mode_switch_bar` (analysis/layout.py:17-108) / KTV Player's search `mode_switch_bar` (search_screen.py:86-147): container with opacity bg + border, active segment PRIMARY bg / white text. Place it in `header_bar` next to the "Active Session" title. Reuse existing `set_tab` / `_switch_to_terminal` logic.

**8. Dynamic FAB per tab; remove the bottom action row** (`screens/session/fab_menu.py`, `notebook_view.py`, `terminal_panel.py`)
The notebook's bottom action row duplicates the FAB (Files chip = Manage Files) and wastes space. Remove `build_action_row` from the notebook body entirely and move everything into the FAB menu, context-aware by active tab:
- **Notebook tab:** Export .ipynb, Import .ipynb, Clear All Outputs, Manage Files, Mount Drive, Auth GCP, Open in Browser, View Logs, Restart Kernel, Stop Session (restart/stop keep their confirm dialogs)
- **Terminal tab:** Manage Files, New Terminal, Clear Terminal, Copy, Paste, Restart Kernel, Stop Session
`build_session_fab` gains a `mode` param; NotebookView and TerminalPanel each register their action handlers into the SessionScreen actions ref (existing `register_actions` pattern, extended to TerminalPanel). Keep `mini=True` so it doesn't block content.

**9. Contrast/theme audit** (`core/theme.py` + sweep)
- Darken `LIGHT_TEXT_DIM` (`#64748B` → ~`#475569`) — this is the "ash" text all over light mode.
- Port SpanInsight's `adaptive_glass_bg()` / `adaptive_glass_border()` helpers (theme.py:137-148) into Colab's theme.py and use them for the session/status cards instead of `with_opacity(..., ON_SURFACE)` which washes out in light mode.
- Sweep remaining hardcoded colors flagged by the audit (settings logs/data sections, home cards, styles.py) onto semantic tokens; ANSI palette and terminal bg stay (intentional, always dark-on-dark).

## Phase 3 — flet_terminal (your package, `/home/onyii/Desktop/kiri-apps/flet-terminal`)

Installed from PyPI (0.2.2, byte-identical to your repo). Work happens in the repo, then `pip install -e` into Colab's venv; version bump to 0.3.0.

**10. Mobile copy/highlight (the big gap)** — today copy only exists on desktop right-click:
- Python (`terminal.py`): add `on_copy` event attr (Dart already fires `triggerEvent("copy", ...)` — currently dead), `get_selection()` async method, `paste()` method.
- Dart (`flet_terminal.dart`): method handlers for `get_selection` (return selected text) and `paste` (read system clipboard → PTY); fire `on_selection_change` on real user selection (currently only fired by search); long-press = select word.
- `extra_keys.py`: add Copy / Paste / Select All / Clear entries to the keys bar settings menu.
- Colab `terminal_panel.py`: wire Copy (`get_selection` → `ft.Clipboard().set` → snack), Paste, Clear into the terminal FAB menu (Phase 2 item 8).
- Dart changes require a Flutter build to test on device — I'll write them carefully; you verify at build time.

**11. Example app modernization** — `examples/flet_terminal_example/src/main.py` still uses old-style `page.add(...)`/`ft.AppBar`. Rewrite it as `@ft.component` + `page.render()` (React-like), matching the architecture of your other apps, so the package demos the current pattern.

**12. Search bar upgrade** (`search_bar.py`) — add match stepping (next/prev using the existing `search(query, start)` support) and a close button.

## Phase 4 — Verify & ship
- `compileall` + `ruff check` clean, full import test, FAB/modal smoke test.
- Manual test pass: run a cell and see output live; blur-render markdown; browse to `/` and back; select → download; upload with proper UI; notifications readable in light+dark; terminal copy/paste/clear from FAB.
- Commit + push Colab and flet-terminal (and update Colab's pyproject pin to `flet-terminal>=0.3.0`).

Execution order: Phase 1 → Phase 2 → Phase 3 → Phase 4, all in this session.