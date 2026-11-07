# Build, CI, Packaging & Config Audit (v2.1.2 → HEAD)

Baseline: tag `v2.1.2` vs `HEAD` (76a9d4b, squash of all changes since). 147 files changed.

---

## Summary Table

| # | Severity | Location | Finding |
|---|----------|----------|---------|
| 1 | **critical** | `.github/workflows/build-all.yml` | Android notification patch steps from commit 50b1fb1 are **missing** — `flet build apk/aab` will fail on Gradle desugaring error |
| 2 | **high** | `README.md:13,34` | Stale references: Flet 0.86 badge (now 1.0.4), ARMv7 APK download link (dropped in 755b201) |
| 3 | **high** | `pyproject.toml:71-72` | Dev dependencies unpinned: `pytest`, `ruff` — no versions, reproducible CI at risk |
| 4 | **medium** | `.github/workflows/build-all.yml:24` | `UV_PYTHON: "3.14"` — Python 3.14 doesn't exist yet (3.13 is current); will fail when 3.14 lands with breaking changes |
| 5 | **medium** | `.python-version` | Pins `3.14` — same issue; should be `3.13` or `3.12` with `uv` managing patch |
| 6 | **medium** | `tests/services/test_version_sync.py:138-150` | `test_the_installed_version_satisfies_each_pin` assumes local env has `jupyter-kernel-client` installed; will fail in clean CI if `uv sync` not run first |
| 7 | **low** | `settings-debug.log` | Committed debug artifact — contains local paths (`C:\Users\nwoki\.zcode\...`) but no secrets |
| 8 | **low** | `.github/workflows/build-all.yml:9` | Workflow defaults `build_version: "2.2.0"` / `build_number: "13"` — drift risk if not updated with release |
| 9 | **info** | `pyproject.toml:6` | `requires-python = ">=3.14"` — should be `>=3.13` or `>=3.12,<3.14` until 3.14 exists |
| 10 | **info** | `.github/workflows/build-all.yml:85,127` | Python version hardcoded to `'3.14'` in `actions/setup-python@v5` — should use `${{ env.UV_PYTHON }}` |
| 11 | **info** | `.gitignore:36` | `version.json` correctly ignored; test handles missing file gracefully (good) |
| 12 | **info** | `scripts/check_elf_alignment.py` | ELF 16KB alignment gate present and correct — no regression |

---

## Detailed Findings

### 1. [critical] Android build missing flet-notifications patch

**Location:** `.github/workflows/build-all.yml` (jobs `build-apk-split` and `build-aab`)

**Changed since 2.1.2:** Commit 50b1fb1 added the patch steps; they were lost in the squash commit 76a9d4b.

**Problem:** The current workflow runs `flet build apk/aab` directly. This fails on first Gradle pass because `flet-notifications` pulls `flutter_local_notifications` which requires core-library desugaring. The old workflow (v2.1.2) did not have this dependency. Commit 50b1fb1 fixed it with a **first-pass → patch → re-run** sequence (ported from sibling project "Sherlock"). That fix is **absent** from HEAD.

**Evidence:** Current workflow lines 99-106 (APK) and 145-152 (AAB) show only a single build step. Missing steps from 50b1fb1:
```yaml
# First pass (generates Android project, allowed to fail)
- name: Build APK — first pass (generates the Android project)
  continue-on-error: true
  ...
  run: uv run flet build apk ... --split-per-abi -v --exclude pyarrow --skip-flutter-doctor
- name: Patch the generated Android project (notifications)
  run: uv run flet-notifications-patch --project-root build/flutter --foreground-service-type dataSync
# Second pass (real build)
- name: Build APK (split per ABI)
  ...
```

**Better way:** Restore the three-step sequence for both `build-apk-split` and `build-aab` jobs. Ensure `flet-notifications-patch` is available (add to dev deps or install ad-hoc).

---

### 2. [high] README.md has stale references

**Location:** `README.md:13,14,34`

**Changed since 2.1.2:** No — README was not updated during the v2.1.2→2.2.0 transition.

**Problem:** Three stale references:
- Line 13: `Built_with-Flet_0.86` badge → should be `Flet_1.0.4`
- Line 14: `Python-3.14` badge → Python 3.14 doesn't exist; should be `3.13` (or remove version badge)
- Line 34: ARMv7 APK download link → ARMv7 was dropped in 755b201 (no pyzmq wheel)

**Evidence:**
```markdown
<img src="https://img.shields.io/badge/Built_with-Flet_0.86-00B0FF...">
<img src="https://img.shields.io/badge/Python-3.14-3776AB...">
| 📱 **ARMv7** (older phones) | [**collabshell-armeabi-v7a.apk**](...) | Legacy 32-bit Android devices |
```

**Better way:** Update badges to `Flet_1.0.4` and `Python-3.13` (or drop version badge). Remove ARMv7 row from download table.

---

### 3. [high] Dev dependencies unpinned in pyproject.toml

**Location:** `pyproject.toml:71-72`

**Changed since 2.1.2:** v2.1.2 had no `[dependency-groups] dev` section; this was added.

**Problem:** 
```toml
dev = [
    "pytest",
    "ruff",
]
```
No version constraints — `uv sync --group dev` will pull latest, risking CI breakage (e.g., pytest 8.x breaking changes, ruff 0.7+ config changes).

**Evidence:** v2.1.2 uv.lock shows `pytest==8.3.3`, `ruff==0.6.9`. Current uv.lock (rev 5) may differ.

**Better way:** Pin to known-good versions:
```toml
dev = [
    "pytest==8.3.3",
    "ruff==0.6.9",
]
```
Or use a constraints file / `uv lock --upgrade-package` workflow.

---

### 4. [medium] Python 3.14 referenced but doesn't exist

**Location:** `.github/workflows/build-all.yml:24,85,127` and `.python-version`

**Changed since 2.1.2:** v2.1.2 already used `3.14` in workflow and `.python-version`; pyproject.toml changed from `>=3.13` to `>=3.14`.

**Problem:** Python 3.14 is not released (3.13 is current as of 2026-11-02). `actions/setup-python@v5` with `python-version: '3.14'` will fail when 3.14 lands (or now, if not available). `UV_PYTHON: "3.14"` tells uv to use 3.14, which may not be installable.

**Evidence:**
```yaml
env:
  UV_PYTHON: "3.14"
  ...
- uses: actions/setup-python@v5
  with:
    python-version: '3.14'
```
```toml
requires-python = ">=3.14"
```
```text
# .python-version
3.14
```

**Better way:** Use `3.13` (current stable) or `3.12` (LTS). Update all three places consistently:
- `UV_PYTHON: "3.13"`
- `python-version: '3.13'`
- `requires-python = ">=3.13"` (or `>=3.12,<3.14`)
- `.python-version` → `3.13`

---

### 5. [medium] test_the_installed_version_satisfies_each_pin assumes installed env

**Location:** `tests/services/test_version_sync.py:138-150`

**Changed since 2.1.2:** This test was added in the diff (new test function).

**Problem:** The test calls `importlib.metadata.version(name)` which reads the *currently installed* environment. In a clean CI runner (before `uv sync`), `jupyter-kernel-client` won't be installed → test fails with `PackageNotFoundError`. The test has a `try/except` but re-raises as `AssertionError`, so it's not a soft skip.

**Evidence:**
```python
def test_the_installed_version_satisfies_each_pin():
    import importlib.metadata as md
    for name, constraint in CRITICAL_PINS.items():
        try:
            version = md.version(name)
        except md.PackageNotFoundError as exc:
            raise AssertionError(f"{name} is not installed") from exc
        ...
```

**Better way:** Either:
- Mark as `@pytest.mark.integration` / require `uv sync` first, or
- Read version from `uv.lock` / `pyproject.toml` instead of installed env, or
- Skip gracefully if not installed: `pytest.skip(f"{name} not installed in test env")`

---

### 6. [low] Committed debug artifact: settings-debug.log

**Location:** `settings-debug.log` (root)

**Changed since 2.1.2:** Added in the diff (new file, binary in v2.1.2 → text in HEAD).

**Problem:** File contains local Windows paths:
```
uv run flet run 2>&1 | tee settings-debug.log
Assets path configured: C:\Users\nwoki\.zcode\workspace\default\ColabShell\src\assets
```

**Evidence:** No secrets, tokens, or credentials — just a local username and workspace path.

**Better way:** Remove from git (add to `.gitignore` if needed for local debugging). The file is 1.3KB — noise in repo history.

---

### 7. [low] Workflow defaults drift risk

**Location:** `.github/workflows/build-all.yml:9-16`

**Changed since 2.1.2:** Defaults updated from `2.1.2`/`12` to `2.2.0`/`13`.

**Problem:** Workflow `workflow_dispatch` inputs default to hardcoded values. If a maintainer triggers a build without overriding, it builds with stale defaults. The `test_workflow_defaults_in_sync` test catches this, but only at test time — not at dispatch time.

**Evidence:**
```yaml
workflow_dispatch:
  inputs:
    build_version:
      default: "2.2.0"
    build_number:
      default: "13"
```

**Better way:** Consider using a `version.txt` or reading from `pyproject.toml` at workflow start, or document that manual dispatch must always override. The test is a good safety net.

---

### 8. [info] pyproject.toml requires-python too aggressive

**Location:** `pyproject.toml:6`

**Changed since 2.1.2:** v2.1.2 had `>=3.13`; changed to `>=3.14`.

**Problem:** `>=3.14` means "3.14 or any future version." When 3.14 releases, it may have breaking changes. Upper bound recommended.

**Better way:** `requires-python = ">=3.13,<3.15"` or `>=3.12,<3.14"` to allow 3.12/3.13 but exclude unknown future.

---

### 9. [info] Workflow hardcodes Python version instead of using env

**Location:** `.github/workflows/build-all.yml:85,127`

**Changed since 2.1.2:** v2.1.2 also hardcoded `'3.14'`.

**Problem:** Two jobs (`build-apk-split`, `build-aab`) hardcode `python-version: '3.14'` instead of `${{ env.UV_PYTHON }}`. If `UV_PYTHON` changes, the jobs diverge.

**Better way:** Use `${{ env.UV_PYTHON }}` in `actions/setup-python@v5` for consistency.

---

### 10. [info] version.json deletion is safe

**Location:** `.gitignore:36`, `tests/services/test_version_sync.py:60-62`

**Changed since 2.1.2:** `version.json` was tracked in v2.1.2; now ignored and deleted.

**Problem:** None — the deletion is intentional and safe. The update feed is meant to be published manually *after* a release is live. The test `test_feed_never_ahead_of_app` gracefully returns if `version.json` doesn't exist locally.

**Evidence:** 
```python
version_file = ROOT / "version.json"
if not version_file.exists():
    return
```

**Better way:** Current approach is correct. No action needed.

---

### 11. [info] ELF 16KB alignment gate intact

**Location:** `scripts/check_elf_alignment.py`, `.github/workflows/build-all.yml:108,154`

**Changed since 2.1.2:** No functional change — script unchanged, workflow calls preserved.

**Problem:** None — the check runs on both APK and AAB artifacts and fails CI if any 64-bit `.so` has `p_align < 16384`.

**Better way:** Current approach is correct. No action needed.

---

### 12. [info] No `__pycache__` or `*.pyc` tracked

**Location:** `.gitignore:6-7`

**Changed since 2.1.2:** Unchanged.

**Verification:** `git ls-files | grep -i pycache` → empty. Good.

---

## Cross-Reference Checks

| Check | Status |
|-------|--------|
| `docs/audit-05-notebook-files-storage.md` (deleted version.json) | Consistent — version.json is correctly ignored and feed is manually staged |
| `docs/dep-01-flet-core.md`, `docs/dep-02-flet-ecosystem.md` (flet_cli usage) | CI uses `uv run flet build` — flet-cli 1.0.4 pinned in pyproject.toml for Windows |
| ARMv7 drop (755b201) | Confirmed: `target_arch = ["arm64-v8a"]` in pyproject.toml; README still has ARMv7 link (Finding #2) |
| Windows icon step restore (d2e498b) | Present in HEAD workflow lines 175-178 — correct |
| Pre-release semantics (0492c8e, 50b1fb1) | Present: `IS_PRERELEASE=true`, `MAKE_LATEST=false` for both tag and SHA builds |
| ELF alignment gate | Present and correct |

---

## Recommended Fix Priority

1. **Restore flet-notifications patch steps** in both Android jobs (critical — blocks Android builds)
2. **Update README badges and ARMv7 link** (high — user-facing misinformation)
3. **Pin pytest/ruff versions** in `pyproject.toml` dev group (high — CI reproducibility)
4. **Fix Python version** from 3.14 → 3.13 in 4 places (medium — future breakage)
5. **Fix `test_the_installed_version_satisfies_each_pin`** to not hard-fail in clean CI (medium)
6. **Remove `settings-debug.log`** from git (low — hygiene)
7. **Use `${{ env.UV_PYTHON }}`** in workflow Python setup (info — consistency)
8. **Add upper bound** to `requires-python` (info — future-proofing)