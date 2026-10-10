# CollabShell — Flet 1.0.3 Road: Milestones & Phases

> **Status:** ROADMAP — phases run strictly in order. Each phase: plan mode → approve → implement → back to plan mode for the next.
> **Standing rules:** document-first; `version.json` FROZEN; match upstream; no unsolicited backup branches.
> **Reference docs:** `00_MASTER_CHANGE_INVENTORY.md` · `findings/upstream-truth.md` · `findings/ui-usage-surface.md` (§5 HOT LIST H1–H17) · `findings/core-services-usage.md` · `findings/tests-packaging-deps.md` (+ `terminal-diff/w038` vs `w039`).

---

## F1 — Pins + build config + terminal upgrade (SDK + packaging, no UI churn) ← NEXT: plan this now

**Goal:** run on Flet 1.0.3 with zero regressions. No border migration, no UI changes.
**Evidence:** inventory §1–§2; B11/B20/B22; terminal §5.

- [ ] F1.1 Pin flip: `flet==1.0.3` + `flet-ads/cli/desktop==1.0.3` + `flet-terminal==0.3.9`; re-lock; verify `uv.lock` stanzas. httpx/rich untouched (already latest).
- [ ] F1.2 Build config: migrate `[tool.flet.app.boot_screen]` → `[tool.flet.boot_screen]` named screen (B11 — legacy fallback REMOVED in 1.0.0); check target_arch/pyzmq comment still holds; dotfile audit (B22 — `.env`/dotfiles now excluded by default; confirm we ship none we need).
- [ ] F1.3 `ft.run` call compat (B2 — `main` vs `target` param) + `init()`-override grep (B18) + `UrlTarget` grep (B21) + atexit/storage-flush review (B20 hard-exit contract).
- [ ] F1.4 Terminal upgrade: adopt 0.3.9 (`MobileTerminal` API, shared Clipboard, `run_task` fix); migrate `terminal_panel.py:30,252-253,340,607` private-internal uses; zero-coverage file — needs new tests + live terminal smoke.
- [ ] F1.5 Regression: full suite green (78+), `flet run` boots, About reports 1.0.3, Android `target_arch` build config intact.

## F2 — Border shorthand migration (17+2 sites, mechanical)

**Goal:** eliminate all 1.0.0-deprecated `border_radius=` (17 sites) + `border_color=` borderless-editor trick (2 sites) before the 1.3.0 removal.
**Evidence:** HOT LIST H1/H2/H4 (verified `V.deprecated` markers in 1.0.3 source).

- [ ] F2.1 Replace 17 `border_radius=` on Dropdown/TextField with `border=OutlineInputBorder(...)` preserving current radii; verify dark-mode rendering (upstream: unset side now themes per-state instead of black).
- [ ] F2.2 Notebook editors' `border_color=TRANSPARENT` trick → `NoInputBorder()` (upstream: actually removes border on all platforms now).
- [ ] F2.3 Component tests for border rendering both states; suite green.

## F3 — Reactive/behavioral verification + test hardening

**Goal:** prove the reconciling/state-matching fixes help us and harden the riskiest suites.
**Evidence:** B15/B19; `test_use_keyboard_shortcuts` page-mock risk; terminal_panel zero coverage.

- [ ] F3.1 Focus/scroll/event spot-checks (the v1.0.0/v1.0.3 fixes target exactly our patterns); property-default read-path audit (None→constant).
- [ ] F3.2 `test_use_keyboard_shortcuts` mock-shape review vs 1.0.3; terminal_panel first coverage (mock runtime, no network).
- [ ] F3.3 Full sweep green; ruff clean; no `version.json` modification.

## F4 — Build/packaging verification (Android + desktop + web deltas)

**Goal:** ship artifacts verified under the new build pipeline.
**Evidence:** B16/B22/B23; `flet-platform-assets` new dep; `check_elf_alignment.py` still stdlib-only.

- [ ] F4.1 Icon/splash generation via `flet-platform-assets` (verify our `assets/icon.png` path + splash behavior change for default icons).
- [ ] F4.2 Android `target_arch` + 16KB alignment re-verified with 1.0.3 client libs.
- [ ] F4.3 `flet run -v` logging + `--` separator passthrough smoke (dev-experience, low risk).

## Ordering rules

1. Strictly sequential, one plan-mode cycle per phase.
2. If a phase uncovers evidence against the upgrade (e.g. terminal API unusable), stop and re-plan — never silently diverge.
3. flet-terminal 0.3.9 CANNOT land without Flet 1.0.x (floor `flet>=1.0.1`) — F1 does both together.
