# ColabShell /docs — Index & Baseline

**Baseline:** tag `v2.1.2` (50fe98b) → HEAD `76a9d4b` (squashed commit of all changes since v2.1.2, **147 files, +31,759 / -1,392 lines**).

**Protocol:** Each finding in `FINDINGS.md` lists **Severity**, `path:line`, **one-line problem**, **fix**, and **source doc(s)**. Deduplicated across all 18 source docs. Top 10 Critical fixes table at top. Sections A–H sorted Critical → High → Medium → Low → Info.

---

## File Index

| File | Type | One-Line Description |
|------|------|----------------------|
| `FINDINGS.md` | **Master** | Severity-ranked, deduplicated master fix list for squashed commit 76a9d4b (all changes since v2.1.2) |
| `audit-01-ai-assistant.md` | Audit | AI Assistant feature (kani backend, model catalog, credits, streaming, in-cell AI, tools, rendering) — 20 findings |
| `audit-02-router.md` | Audit | LM-Router client stack (router.py, router_engine.py, router_watchdog.py, protocol compliance, turn ledger, watchdog) — 12 findings |
| `audit-03-ads-premium-license.md` | Audit | Ads, Premium, Credits, Licensing/Wallet (ad_service, premium_service, credit_service, license_service, license_token, wallet_dialog) — 19 findings |
| `audit-04-colab.md` | Audit | Colab remote-session code (auth, session_ops, execution, files_ops, terminal_client, usage_ops, vm_ops) — 13 findings |
| `audit-05-notebook-files-storage.md` | Audit | Notebook, Files, Scripts, Local Storage, Updates (ipynb_converter, file_read, storage_service, script_runner, changelog, version.json) — 13 findings |
| `audit-06-settings-ui-core.md` | Audit | App Shell, Settings Screen, Core/State/Hooks, Remaining Components (Flet 1.0.4 lifecycle violations, page.update in use_effect, hooks) — 20 findings |
| `audit-07-build-ci-config.md` | Audit | Build, CI, Packaging & Config (workflow missing flet-notifications patch, stale README, unpinned deps, Python 3.14 refs) — 14 findings |
| `audit-08-ai-in-session.md` | Audit | Session-level AI integration and cell actions |
| `audit-09-ai-output-rendering.md` | Audit | Output rendering, ANSI escape sequences and markdown parser |
| `audit-10-model-loading-ux.md` | Audit | Model picker, status watchdog and header pill synchronization |
| `audit-11-session-store-lock.md` | Audit | Session store lock & concurrency analysis |
| `audit-12-background-performance.md` | Audit | Background tasks & performance audit (keepalive, credit sweep, router watchdog, reconcile, storage) |
| `dep-01-flet-core.md` | Dep | Flet 1.0.4 usage audit — critical `page.update()` in `use_effect`, hook misuse, missing `on_unmounted`, unexposed Flet APIs — 12 findings |
| `dep-02-flet-ecosystem.md` | Dep | Flet satellite packages (flet_ads, flet_notifications, flet_desktop, flet_terminal, flet_platform_assets, flet_cli) — gaps, dead deps, rewarded ad policy violations — 6 package audits |
| `dep-03-colab-libs.md` | Dep | google-colab-cli 0.7.4 API reference & gap analysis — auth duplication, session_ops reimplements CLI commands, singleton bypass, terminal endpoint mismatch — 30 gaps |
| `dep-04-ai-libs.md` | Dep | AI libraries (kani 1.10.0, openai 2.54.0, httpx 0.28.1, tiktoken 0.14.0) — streaming misuse, hand-rolled tool schemas, api_type hardcoded, tokenizer workaround — 17 gaps |
| `dep-05-jupyter-libs.md` | Dep | Jupyter stack (nbformat 5.11.1, jupyter_client 8.10.0, jupyter_kernel_client 0.9.0, watchdog 6.0.0) — execution_count loss, missing validation, MIME type gaps, output rendering incomplete — 18 gaps |
| `dep-06-misc-libs.md` | Dep | Misc libraries (requests, tornado, rich, flet_terminal) — sync requests in async, manual WS ping, custom color maps, no foreground service — 10 gaps |
| `ref-01-ddgs-patterns.md` | Ref | DDGS reference patterns (gold standard) — ads service, premium card, wallet/credits, settings sections, app shell, license/crypto — 10 priority adoption items |
| `ref-02-router-protocol.md` | Ref | Router protocol reference (client contract for Kiri Router / lm-router) — HTTP API, server lifecycle, ledger, model catalog, streaming, perfect client checklist — 33 checklist items |
| `research-01-colab-cli-upstream.md` | Research | google-colab-cli upstream & idle/session lifecycle — 0.7.4→0.7.5 no changes, keep-alive removed, token refresh 5-min margin, backend-driven liveness — 4 direct answers |
| `research-02-wakelock-and-flet-versions.md` | Research | Wake lock, Flet versions, flet_ads rewarded usage — Flet 1.0.5 adds Wakelock, flet_notifications 1.1.0 adds foreground service, flet_ads has NO RewardedAd — 4 recommendations |
| `research-03-kernel-liveness.md` | Research | Kernel/session liveness in Jupyter stack & Colab — no client-side heartbeat for remote, server in charge, kernel activity resets idle timer, error mapping for 404/401/WS close — 4 recommendations |

---

## Baseline Summary

| Metric | Value |
|--------|-------|
| **Baseline tag** | `v2.1.2` (50fe98b) |
| **HEAD** | `76a9d4b` (squashed commit) |
| **Files changed** | 147 |
| **Lines added** | +31,759 |
| **Lines removed** | -1,392 |
| **Scope** | All changes since v2.1.2 — AI assistant, router client, Colab sessions, notebook/files/scripts, UI/Flet lifecycle, build/CI, dependency upgrades |

---

## Protocol for Reading Findings

1. **Start with Top 10 Critical Fixes** table in `FINDINGS.md` — these block releases or cause data loss.
2. **Read by workstream** (Sections A–H) — each sorted Critical → High → Medium → Low → Info.
3. **Each entry** = `Severity` + `path:line` + `Problem` + `Fix` + `Source doc(s)`.
4. **Deduplicated** — e.g., `page.update()` in `use_effect` appears in `audit-06`, `dep-01`, `dep-02`; kept once with all sources cited.
4. **Reference apps** — DDGS (`/home/maikel/Desktop/kiri-apps/DDGS`) is the gold standard for ads/premium/license/router patterns; `lm-router` + `kiri-router` define the router protocol.

---

## Quick Links by Area

| Area | Primary Docs |
|------|--------------|
| **Ads / Premium / License / Credits** | `audit-03`, `ref-01` §1–3, `research-02` §3 |
| **AI Assistant / Router Client** | `audit-01`, `audit-02`, `dep-04`, `ref-02` |
| **Colab Sessions / Execution / Terminal** | `audit-04`, `dep-03`, `research-01`, `research-03` |
| **Notebook / Files / Scripts / Storage** | `audit-05`, `dep-05` |
| **UI / Flet 1.0.4 Lifecycle / Settings** | `audit-06`, `dep-01`, `dep-02` |
| **Build / CI / Packaging / Config** | `audit-07` |
| **Dependency Upgrades** | `dep-01`..`dep-06`, `research-02` §2 |
| **DDGS Reference Patterns** | `ref-01` |
| **Router Protocol Checklist** | `ref-02` §7 |

---

## Verification

```bash
ls -1 /home/maikel/Desktop/kiri-apps/ColabShell/docs/
# Should show 20 files (18 source + FINDINGS.md + this README.md)
```