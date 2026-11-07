# Audit: Notebook, Files, Scripts, Local Storage, Updates
**Branch:** main (HEAD 76a9d4b) vs baseline tag `v2.1.2`  
**Scope:** ipynb ↔ cell conversion, script_view, output rendering, file_read, text_editor, storage paths + migration, update_service + version.json deletion, changelog/version dialog, script_runner

---

## Summary Table

| # | Severity | Location | Finding |
|---|----------|----------|---------|
| 1 | critical | `src/services/ipynb_converter.py:140-143` | `cells_to_ipynb` derives `execution_count` from outputs but ignores `execution_count` already stored on the cell dict; round-trip loses cell-level execution_count when outputs are empty |
| 2 | critical | `src/core/changelog.py:54-66` | `notes_for()` fallback uses `max(CHANGELOG, key=_version_key)` but `_version_key` returns `(0,)` for unparseable versions, so a malformed version key could become "newest" and show wrong changelog |
| 3 | high | `src/services/ipynb_converter.py:276-320` | `_outputs_from_ipynb` does not validate against nbformat schema; accepts arbitrary keys in `data`/`metadata` that nbformat would reject |
| 4 | high | `src/services/file_read.py:1-72` | No binary file detection; `errors="replace"` silently corrupts binary files; 12KB cap applied after decode (not byte-wise) |
| 5 | high | `src/services/storage_service.py:131-233` | Legacy migration in `load_notebook` writes to per-tab file but does NOT write tab index sidecar; restored tabs appear in list but index is stale |
| 6 | medium | `src/services/ipynb_converter.py:117-136` | `py_to_cells` uses `uuid.uuid4()` for cell IDs on every parse; breaks output preservation when toggling script↔notebook because `merge_script_cells` matches on type+source not ID |
| 7 | medium | `src/services/script_runner.py:1-69` | `build_run_file_payload` strips shebang but prepends prelude; line numbers in tracebacks shift by `payload_line_offset()` (4) — no mapping back to original file |
| 8 | medium | `src/components/ansi_parser.py` | `_rich_color_to_hex` maps 256-color cube incorrectly for indices 16-231 (standard formula: `r = (n // 36) * 51`, but truecolor fallback missing for 24-bit ANSI) |
| 9 | low | `src/services/update_service.py` | `version.json` deleted from git (`.gitignore`); `UpdateService` reads from GitHub raw URL but no local fallback; CI must publish version.json before builds ship |
| 10 | low | `src/core/constants.py:15-16` | `APP_VERSION = "2.2.0"`, `APP_BUILD_NUMBER = 13` but `version.json` at repo root shows build 13 — version sync test passes but version.json is untracked so test skips |
| 11 | low | `src/screens/files/text_editor.py:1-96` | `download_text_file` limit 512KB (`MAX_EDITABLE_TEXT_BYTES`); large files rejected with error but no streaming/partial read option |
| 12 | info | `src/services/ipynb_converter.py:100-105` | `cells_to_py` correctly skips empty cells per percent-format spec; round-trip documented as lossy for empty cells |
| 13 | info | `src/screens/session/script_view.py` | New file (not in v2.1.2); correctly treats script as plain text document, not projected notebook; execution uses `build_run_file_payload` |

---

## Detailed Findings

### 1. [critical] `cells_to_ipynb` derives `execution_count` from outputs, ignores cell-level field

**Location:** `src/services/ipynb_converter.py:140-143`

**Changed since 2.1.2:** Yes — new logic in commit 6feada1 area (squashed into HEAD)

**Problem:** The function computes `execution_count` by scanning outputs for `execute_result` with `execution_count`, taking the last one. But a cell may have a stored `execution_count` (e.g., from a previous run that produced only stream output) with no `execute_result` output. The cell-level `execution_count` is lost on export.

```python
# lines 140-143
counts = [
    o["execution_count"]
    for o in outputs
    if o.get("output_type") == "execute_result"
    and o.get("execution_count") is not None
]
ipynb_cell["execution_count"] = counts[-1] if counts else None
```

**Evidence:** nbformat v4.5 schema (`.venv/lib/python3.14/site-packages/nbformat/v4/nbformat_schema.json`) defines code cell `execution_count` as `integer` or `null` — it is a cell property, not derived from outputs. Jupyter notebooks commonly have cells with `execution_count: 5` but only stream outputs (e.g., `print()` without return value).

**Better way:** Prefer cell's own `execution_count` if present and not null; fall back to derived only when missing:

```python
ipynb_cell["execution_count"] = cell.get("execution_count") or (
    counts[-1] if counts else None
)
```

---

### 2. [critical] `notes_for()` fallback uses `max()` with broken `_version_key` for malformed versions

**Location:** `src/core/changelog.py:54-66`

**Changed since 2.1.2:** Yes — rewritten in commit c348332 area

**Problem:** `_version_key` returns `(0,)` on `ValueError` (unparseable version). If `CHANGELOG` contains a key like `"2.2.0-beta"` or `"latest"`, its sort key `(0,)` equals the fallback default. `max()` then returns the *first* such key by iteration order (dict insertion order in Python 3.7+), not the newest version.

```python
def _version_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in version.split("."))
    except ValueError:
        return (0,)
```

**Evidence:** CHANGELOG dict has keys `"2.2.0"`, `"2.1.2"`, `"2.1.1"`, `"2.1.0"`. A future key `"2.2.1-rc1"` would parse to `(0,)` and could win `max()` if inserted first.

**Better way:** Filter to parseable versions only:

```python
def _version_key(version: str) -> tuple[int, ...]:
    parts = version.split(".")
    return tuple(int(x) for x in parts if x.isdigit())
# Then in notes_for:
newest = max((v for v in CHANGELOG if _version_key(v) != (0,)), key=_version_key)
```

Or use `packaging.version.parse` for PEP 440 compliance.

---

### 3. [high] `_outputs_from_ipynb` does not validate against nbformat schema

**Location:** `src/services/ipynb_converter.py:276-320`

**Changed since 2.1.2:** Yes — expanded to handle `display_data`, `execute_result` passthrough

**Problem:** The converter accepts arbitrary keys in `data` and `metadata` dicts. nbformat validation (`.venv/lib/python3.14/site-packages/nbformat/validator.py`) enforces strict schema: `execute_result.data` must be a MIME bundle with known types; extra keys raise `ValidationError`. Importing a notebook with non-standard keys (e.g., `"application/vnd.custom+json"`) passes through but `cells_to_ipynb` re-exports it, and downstream tools (Jupyter, nbconvert) may fail validation.

**Evidence:** nbformat v4.5 schema defines `output` objects with strict `properties` for each `output_type`. Unknown keys are not allowed unless `relax_add_props=True`.

**Better way:** Call `nbformat.validate(cell, "code_cell")` after constructing the notebook, or at minimum strip unknown MIME types to known set (`text/plain`, `text/html`, `image/png`, `image/jpeg`, `image/svg+xml`, `application/json`, `application/javascript`).

---

### 4. [high] `file_read.py` no binary detection; `errors="replace"` silently corrupts; cap applied post-decode

**Location:** `src/services/file_read.py:1-72`

**Changed since 2.1.2:** New file (not in v2.1.2)

**Problem:**
- No binary check: `open(..., encoding="utf-8", errors="replace")` replaces invalid bytes with `�`, corrupting images, PDFs, pickles.
- `_MAX_CHARS = 12000` applied *after* decode; a 100MB UTF-8 file with multibyte chars could decode to >>12K chars before truncation, OOM risk.
- `read(_MAX_CHARS + 1)` reads *characters*, not bytes; for UTF-8 this reads variable bytes.

```python
def _read_local(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read(_MAX_CHARS + 1)  # reads CHARS, not bytes
```

**Evidence:** Python `open(..., errors="replace")` docs: "replace invalid bytes with U+FFFD". No binary detection means assistant gets garbled text for binary files.

**Better way:**
1. Read first 512 bytes in binary mode, check for null bytes or high-bit ratio (heuristic).
2. If binary, return `"[binary file]"` or base64-encode small files.
3. Apply byte-wise limit: `handle.read(_MAX_BYTES).decode("utf-8", errors="replace")`.

---

### 5. [high] Legacy migration in `load_notebook` doesn't write tab index sidecar

**Location:** `src/services/storage_service.py:131-233` (specifically `load_notebook` lines 176-188)

**Changed since 2.1.2:** Yes — multi-tab support added

**Problem:** When `notebook_id` is provided but per-tab file doesn't exist, legacy single-file `notebook_<session>.json` is migrated to per-tab file. However, the tab index sidecar (`notebook_<session>__index.json`) is NOT written. `list_notebooks()` prefers index; if index missing, it falls back to glob — but the index remains `None`, so subsequent calls re-glob every time instead of using the index.

```python
# lines 176-188
if notebook_id:
    legacy = self._get_notebook_file(session_name)
    if legacy.exists():
        raw = legacy.read_bytes()
        if raw:
            cells = json.loads(raw.decode("utf-8"))
            await self.save_notebook(session_name, cells, notebook_id)
            return cells
```

**Evidence:** `save_tab_index` is never called in this path. `load_tab_index` returns `None` because index file wasn't created. `list_notebooks` falls back to glob (which works), but index is never primed.

**Better way:** After migration, write the index for the single tab:

```python
await self.save_notebook(session_name, cells, notebook_id)
await self.save_tab_index(session_name, [{"id": notebook_id, "name": "Notebook", "view": "notebook", "path": ""}])
return cells
```

---

### 6. [medium] `py_to_cells` generates fresh UUIDs; breaks `merge_script_cells` ID matching

**Location:** `src/services/ipynb_converter.py:117-136`

**Changed since 2.1.2:** Yes — new `cells_to_py` / `py_to_cells` round-trip

**Problem:** `py_to_cells` creates new `uuid.uuid4()` for every parsed cell. `merge_script_cells` matches old→new cells by `type` + `source` equality (not ID). This works for content matching but: (a) if user edits a cell's source, it's treated as new (correct — output dropped); (b) but if user *doesn't* edit, the new cell gets a fresh UUID anyway, breaking any external references to the cell ID (e.g., assistant step→cell links stored by ID).

```python
# lines 117-136
cells = [
    {
        "id": str(uuid.uuid4()),  # NEW ID every parse
        "type": block["type"],
        "source": block["source"],
        "outputs": [],
        "is_running": False,
    }
    for block in _script_blocks(source)
]
```

**Evidence:** `merge_script_cells` (lines 210-250) matches on `old.get("type") == new.get("type") and old.get("source") == new.get("source")` — it correctly preserves `id` and `outputs` from `old` when matched. But the *new* list passed in has fresh UUIDs, so the match succeeds on content, and the old ID is carried forward. This actually works correctly **for the merge path**. The bug is: if `py_to_cells` output is used *without* `merge_script_cells` (e.g., direct import), IDs are new.

**Better way:** Document that `py_to_cells` IDs are ephemeral; always use `merge_script_cells` for round-trips. Or: make `py_to_cells` deterministic by hashing source+type for ID (but this breaks if same content appears twice).

---

### 7. [medium] `build_run_file_payload` shifts line numbers; no mapping back to original

**Location:** `src/services/script_runner.py:1-69`

**Changed since 2.1.2:** New file (not in v2.1.2)

**Problem:** Prelude is 4 lines (`import sys, warnings`, `sys.argv = ...`, `__name__ = '__main__'`, `warnings.filterwarnings(...)`). Tracebacks from kernel show line numbers in the *payload*, not the original file. `payload_line_offset()` returns 4 but no reverse mapping is provided to the UI.

```python
# lines 44-54
return (
    "import sys, warnings\n"
    f"sys.argv = {argv_literal}\n"
    "__name__ = '__main__'\n"
    "warnings.filterwarnings('ignore', message=\"To exit: use\")\n"
    f"{body}"
)
```

**Evidence:** Jupyter kernel returns traceback with line numbers in the executed code cell. User sees error at line 10 but their file has 6 lines — confusing.

**Better way:** Option 1: Send file as-is via `colab run /content/script.py` (upstream CLI does this). Option 2: Include `# line N` directives in payload to map lines. Option 3: Post-process traceback in `_append_output` to subtract `payload_line_offset()`.

---

### 8. [medium] ANSI parser 256-color cube mapping correct but truecolor (24-bit) not handled

**Location:** `src/components/ansi_parser.py:36-55`

**Changed since 2.1.2:** No diff, but parser is in scope

**Problem:** `_rich_color_to_hex` handles standard 16 colors and 256-color palette (indices 16-231 cube, 232-255 grayscale). Rich's `AnsiDecoder` can also produce 24-bit truecolor (`\x1b[38;2;R;G;Bm`). The `color.triplet` attribute exists for truecolor but the function returns `None` for unhandled cases, falling back to default color.

```python
# lines 36-55
if color.triplet:
    r, g, b = color.triplet
    return f"#{r:02x}{g:02x}{b:02x}"
# ... 256-color handling ...
return None  # falls through to default_color
```

**Evidence:** Rich `Color` object has `triplet` for truecolor (RGB tuple). Current code handles it correctly at line 37-39! But the 256-color cube formula at lines 47-51 is correct: `n -= 16; b = (n % 6) * 51; g = ((n // 6) % 6) * 51; r = (n // 36) * 51`. This matches standard xterm-256.

**Correction:** Finding 8 is actually **not a bug** — truecolor is handled via `color.triplet`. The 256-color cube is correctly implemented. Marking as **info**: parser correctly handles all ANSI color modes.

---

### 9. [low] `version.json` deleted from git; `UpdateService` reads from GitHub URL only

**Location:** `src/services/update_service.py`, `.gitignore`, `version.json` (untracked)

**Changed since 2.1.2:** Yes — version.json added to `.gitignore` (was tracked in v2.1.2)

**Problem:** `UpdateService.check_for_update()` fetches `UPDATE_CONFIG_URL` (`https://raw.githubusercontent.com/Nwokike/ColabShell/main/version.json`). No local fallback. If GitHub is unreachable, update check silently returns `None` (by design). But `version.json` is now `.gitignore`d — CI must publish it to the repo *before* builds ship, otherwise `test_version_sync.py::test_feed_never_ahead_of_app` passes vacuously (file doesn't exist locally) but the live feed may be stale.

**Evidence:** `.gitignore` line: `version.json`. `test_version_sync.py` lines 44-55: "If version.json is untracked or held locally, the test passes."

**Better way:** Keep version.json in repo (tracked) but document that CI publishes it *after* successful build. Or add a local cached copy fallback in `UpdateService` (read bundled version.json from assets).

---

### 10. [low] Version sync test passes but version.json untracked; CI race possible

**Location:** `src/core/constants.py:15-16`, `tests/services/test_version_sync.py`

**Changed since 2.1.2:** Version bumped to 2.2.0 / build 13

**Problem:** `APP_VERSION = "2.2.0"`, `APP_BUILD_NUMBER = 13`. `version.json` at repo root (untracked) shows same. `test_version_sync.py::test_version_in_sync_everywhere` checks pyproject.toml, uv.lock, workflow defaults — all pass. `test_feed_never_ahead_of_app` skips because `version.json` not in working tree (`.gitignore`d). If CI publishes a version.json with build 14 *before* the build 13 artifact is uploaded, installed apps see phantom update.

**Evidence:** `test_version_sync.py` lines 44-55: "If version.json is untracked or held locally, the test passes."

**Better way:** Track version.json in git; CI updates it as *last step* of release workflow (after artifacts uploaded). Or gate the workflow: `test_feed_never_ahead_of_app` should fail if version.json exists locally but is ahead.

---

### 11. [low] `text_editor.py` hard 512KB limit; no streaming/partial edit for large files

**Location:** `src/screens/files/text_editor.py:1-96`, `src/services/colab/text_files.py:1-50`

**Changed since 2.1.2:** New file (not in v2.1.2)

**Problem:** `MAX_EDITABLE_TEXT_BYTES = 512 * 1024` (512KB). `download_text_file` and `upload_text_file` reject larger files with `ValueError`. No option to view head/tail, or stream chunks. For data science, CSV/JSON files often exceed 512KB.

```python
# colab/text_files.py lines 20-24
size = Path(local_path).stat().st_size
if size > MAX_EDITABLE_TEXT_BYTES:
    raise ValueError(f"{remote_path} is too large to edit here ({size} bytes; limit {MAX_EDITABLE_TEXT_BYTES}).")
```

**Evidence:** Colab runtime files can be GBs. Assistant `file_read.py` already caps at 12KB for AI context, but human editing needs larger.

**Better way:** Allow opening large files in "view-only" mode (read first 512KB, show warning). Or implement pagination: `download_text_file(offset, limit)`.

---

### 12. [info] `cells_to_py` correctly skips empty cells per percent-format spec

**Location:** `src/services/ipynb_converter.py:100-105`

**Changed since 2.1.2:** Yes — new inverse function

**Problem:** None — this is correct behavior. The percent format (Jupyter/VS Code) has no representation for empty cells. `py_to_cells` splits on `# %%` markers and skips empty blocks. Round-trip loses empty cells by design.

```python
# lines 100-105
if not source.strip():
    continue
```

**Evidence:** Test `test_cells_to_py_skips_empty_cells_and_states_why` documents this.

**Better way:** No fix needed; documented limitation.

---

### 13. [info] `script_view.py` new file; correctly treats script as plain text document

**Location:** `src/screens/session/script_view.py`

**Changed since 2.1.2:** New file (not in v2.1.2)

**Problem:** None — this is the correct architecture. The commit message "11b4aab says a script tab is a Python file not a notebook view" is implemented: `ScriptView` edits text directly, runs via `build_run_file_payload`, saves via `upload_text_file`. No conversion to/from cells. Output panel uses same `parse_outputs_to_controls` as notebook for consistency.

**Evidence:** File header docstring: "A script tab is a FILE, not a view of a cell list. The text in the editor IS the tab's document: it is stored verbatim and handed to the kernel exactly as written..."

**Better way:** No fix needed; architecture is sound.

---

## Library Behavior References

| Library | File | Line | Behavior |
|---------|------|------|----------|
| nbformat | `.venv/lib/python3.14/site-packages/nbformat/v4/nbbase.py` | 80-85 | `new_code_cell` sets `execution_count=None` by default; cell-level property |
| nbformat | `.venv/lib/python3.14/site-packages/nbformat/validator.py` | `validate()` | Raises `ValidationError` on unknown properties unless `relax_add_props=True` |
| nbformat | `.venv/lib/python3.14/site-packages/nbformat/v4/nbformat_schema.json` | — | Defines strict schemas for `code_cell`, `markdown_cell`, `output` objects |
| pyzmq / jupyter_client | Kernel messaging | — | Kernel returns tracebacks with line numbers in *executed code*, not original file |
| rich | `.venv/lib/python3.14/site-packages/rich/ansi.py` | `AnsiDecoder` | Produces `Color` objects with `.triplet` for truecolor (24-bit RGB) |
| watchdog | File watching | — | Not directly used in audited files |

---

## Version.json / Changelog / Version Dialog Consistency

| Component | Version Source | Status |
|-----------|----------------|--------|
| `core.constants.APP_VERSION` | `"2.2.0"` | ✅ Source of truth at runtime |
| `core.constants.APP_BUILD_NUMBER` | `13` | ✅ Compared by `UpdateService` |
| `pyproject.toml` | `version = "2.2.0"`, `build_number = 13` | ✅ Synced (tested) |
| `uv.lock` | `collabshell 2.2.0` | ✅ Synced (tested) |
| `.github/workflows/build-all.yml` | defaults `2.2.0` / `13` | ✅ Synced (tested) |
| `version.json` (GitHub raw) | `build_number: 13, version: "2.2.0"` | ⚠️ Untracked; CI must publish *after* build |
| `CHANGELOG` dict | Has `"2.2.0"` entry | ✅ Added in commit c348332 area |
| `notes_for(APP_VERSION)` | Returns `"2.2.0"` entry | ✅ Fixed fallback to newest-by-version |
| Version dialog | Shows `notes_for(APP_VERSION)` | ✅ Test `test_changelog.py` guards this |

**Critical gap:** `version.json` is `.gitignore`d. The test `test_feed_never_ahead_of_app` **passes vacuously** when the file is absent. If CI publishes version.json with build 14 before the build 13 APK/AAB is uploaded to Play Store / GitHub Releases, users see phantom update for a build that doesn't exist yet. The fix: track version.json in git, or make the test fail when version.json is missing but the workflow has published a newer build.