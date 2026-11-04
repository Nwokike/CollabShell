# Investigate-06 — Banner ad placement & Copy Output visibility

**Repo:** `/home/maikel/Desktop/kiri-apps/CollabShell` — HEAD `0dfa74e` = tag **v2.2.0** (build 15, "one commit over v2.1.2"). Comparison baseline: tag **v2.1.2** (`50fe98b`). Gold-standard reference: DDGS at `/home/maikel/Desktop/kiri-apps/DDGS/src/`.
**Date:** 2026-11-04. Read-only investigation; this file is the only artifact.

---

## 1. Banner call-site inventory (current HEAD v2.2.0, with v2.1.2 / DDGS comparison)

There are exactly **two** banner constructors, both mobile-only and both collapsing to a 0x0 container on desktop/web and for premium users:

| Constructor | Location | Notes |
|---|---|---|
| `build_banner_ad(page, unit_id=None)` | `src/core/styles.py:108-163` | The one every UI surface uses. Glass-wrapped `fta.BannerAd(unit_id, 320, 50)`; returns `ft.Container(width=0, height=0)` when `page.platform` is not ANDROID/IOS or `state.is_premium`. |
| `AdService.get_banner_ad()` | `src/services/ad_service.py:138-165` | **Dead in production UI** — the only callers are `tests/test_premium.py:72,85`. Same 0x0 gating (premium / no `flet_ads` / not mobile / consent). v2.1.2 also had it at `ad_service.py:105`, equally uncalled by screens. |

### Call sites of `build_banner_ad` in v2.2.0 (all verified by grep)

| Surface | File:line (v2.2.0) | Position in layout | v2.1.2 | DDGS equivalent |
|---|---|---|---|---|
| Home tab | `src/screens/home/__init__.py:341` and `:343` | Inline in the scroll column: after the sessions list, and after the features section | `:325`, `:327` (same inline positions) | `DDGS/src/screens/home_screen.py:853` (after category chips) and `:900` (after features) — same pattern |
| Session selector tabs (notebook/terminal/files list) | `src/screens/session_selector.py:86` | Near the **top**: after the "New session" button, above the `ACTIVE SESSIONS` header | `:86` (unchanged) | n/a |
| Files screen | `src/screens/files/__init__.py:598` | Near the **top**: directly after toolbar/progress/divider, above the file body | `:482` (same position) | n/a |
| Settings screen | `src/screens/settings/__init__.py:93` and `:99` | Two `("SPONSOR", lambda ...: build_banner_ad(page))` sections inline between APPEARANCE/AUTHENTICATION and ASSISTANT, and between SESSION BEHAVIOR and ADVANCED | `:32`, `:36` (same) | `DDGS/src/screens/settings_screen.py:160,170,178` — same inline SPONSOR sections |
| **History screen** (session event log) | `src/screens/history/__init__.py:325` | **Bottom** of the scroll column, after the `EVENTS` list container — the screen's ONLY ad | `:302` — also bottom (no change in 2.2.0) | `DDGS/src/screens/history_screen.py:274` — also bottom |
| **Notebook cells** | `src/screens/session/notebook_view.py:1436` (inside `if (i + 1) % 2 == 0:` at `:1435` — one banner after every 2nd cell) and `:1576` (bottom of `notebook_body`, before the spacer/focus sink) | Per-2-cells + bottom | `:527` and `:548` — identical semantics, only line numbers moved | n/a (DDGS has no notebook) |
| **Export-notebook dialog** | none — `_show_export_dialog` at `src/screens/session/notebook_view.py:1083`, `ft.AlertDialog` at `:1102`, content column with the `.ipynb` / `.py` ListTiles, `Cancel` action: **no banner** | — | v2.1.2 had **no dialog at all**: export was a direct `_export_ipynb` (`v2.1.2` `notebook_view.py:278-307`); the format-picker dialog is new in 2.2.0 and shipped without an ad | n/a |
| History screen "Export as .ipynb" button | `src/screens/history/__init__.py:304` triggers `_on_export` (`:77`), which gates the export behind a **rewarded interstitial**: `await services.ad_service.show_rewarded_interstitial(on_close=_do_export)` at `:100` | — | identical in v2.1.2 | DDGS gates wallet ad-top-up similarly |
| **Chat / assistant view** | **none** — `src/screens/assistant_view.py` has no `build_banner_ad`/ad import at all. View = header + transcript list + composer (`assistant_view.py:474-488`); `_render` (`:1198-1216`) and `_render_assistant` (`:1240+`) append no ad | v2.1.2: also none | **DDGS DOES**: `DDGS/src/screens/chat_screen.py:1629-1653` `_pooled_ad(slot)` + insertion at `:1685-1689` — a pooled banner after every AI reply (`BANNER_AD_EVERY_N_REPLIES = 1`, `:51`), never as the last row |
| Assistant chats history dialog | `src/screens/assistant_history.py:30 show_history_dialog`, `AlertDialog` at ~`:137` — no banner | file is new-ish; no ad in v2.1.2 either | n/a | n/a |
| App shell / main | none — `src/app_shell.py` builds `Column[header_bar, screen]` (`:668-676`); `src/main.py` mentions "banner" only in a comment about the update banner (`:575`) | same in v2.1.2 | DDGS app shell: no app-level banner either |

**v2.1.2 → v2.2.0 diff summary for banners:** no placement changed anywhere. The only banner-related delta in 2.2.0 is the new export-format dialog (`_show_export_dialog`) and the new AI-step output widget (`src/components/ai_step_output.py` did not exist at v2.1.2), neither of which carries an ad.

---

## 2. Correct placement rule + fix list per surface

**Derived rule** (owner statement + existing codebase pattern + DDGS reference):

1. **One banner per major screen, inline in the content flow near the top** — that is the established CollabShell pattern (`files:598` right after the toolbar, `session_selector:86` right after the CTA, `home:341/343` inline, `settings:93/99` SPONSOR sections). A single banner parked at the very bottom of a scroll column (history) reads as an afterthought and is the complaint.
2. **Action dialogs that gate a valuable action (export) carry a banner inside the dialog.**
3. **Notebook cells keep their existing placement** (every 2nd cell + bottom) — owner: "already set, don't touch".
4. **Chat gets NO per-reply banner** — the app-level (tab-screen) banners already exist; do not port DDGS's `_pooled_ad` per-reply banners into `assistant_view`.
5. All banners go through `build_banner_ad` (mobile-only, 0x0 for premium/desktop) — never raw `fta.BannerAd` in screens.

**Fix list:**

| # | Surface | Fix | Location |
|---|---|---|---|
| F1 | History screen | Move the single `build_banner_ad(page)` from the bottom (`:325`, after the EVENTS container) to the **top** of the screen column — above the filter/export bar — matching the files/session_selector top placement. (Alternative if DDGS parity is preferred over the owner's complaint: keep at bottom as DDGS `history_screen.py:274` does — but the owner explicitly flags "only one ad and it's at the BOTTOM", so top is the recommended fix. Do NOT add a second banner.) | `src/screens/history/__init__.py:325` |
| F2 | Export-as-ipynb dialog (notebook export) | **Add** `build_banner_ad(page)` inside the `AlertDialog` content column of `_show_export_dialog`, after the `.ipynb`/`.py` ListTiles (before `actions`). It collapses to 0x0 on desktop/premium automatically. Note: the history screen's export already shows a rewarded interstitial on close (`history/__init__.py:100`) — the dialog banner covers the notebook-export path, which today has no ad at all. | `src/screens/session/notebook_view.py:1083-1133` (AlertDialog at `:1102`) |
| F3 | Chat AI markdown reply | **Nothing to remove today** — v2.2.0 and v2.1.2 both have zero banners in `assistant_view.py`. Rule: keep it that way; the app-level banner lives on the tab screens (home/files/…). Do not port DDGS's per-reply pooled ads (`chat_screen.py:1629-1690`). Optionally add a comment in `_render`/`_render_assistant` pinning the rule so a future DDGS port doesn't add per-reply banners. | `src/screens/assistant_view.py:1198-1216`, `:1240+` |
| F4 | Notebook cell outputs | **Leave as-is**: per-2-cells banner `notebook_view.py:1435-1436` and bottom banner `:1576` (identical semantics to v2.1.2 `:527/:548`). | `src/screens/session/notebook_view.py` |
| F5 | Hygiene | `AdService.get_banner_ad()` (`src/services/ad_service.py:138`) is dead production code (only tests call it) and duplicates `build_banner_ad`. Either route UI through it or delete it; today all screens use `core/styles.py:108`. | `src/services/ad_service.py:138` |

---

## 3. Copy-button visibility rule + where "None idle" comes from

### Where the Copy Output button is rendered today

| Surface | Location | Current condition |
|---|---|---|
| Notebook cell output panel | `src/components/notebook_cell/__init__.py:311-344` — `output_actions` Row; Copy Output `IconButton(COPY_ALL_ROUNDED, tooltip="Copy Output")` at `:329-334`, wired to `_copy_output_task` (`:139-140` → `copy_output(page, list(cell.outputs))`) | The whole `output_panel` is `visible=bool(output_controls) or cell.is_running` (`:367`). So **while a cell is running with zero outputs yet, the panel — including Copy Output — is visible** and tapping it hits the `"No output to copy."` snack. When idle + empty, the panel is hidden. |
| AI tool step in chat | `src/components/ai_step_output.py:168-189` — `if page is not None:` appends the Copy Output button **unconditionally** (`:174-180`); `elif outputs:` (`:182-189`) appends a *disabled* copy button (`on_click=None`) | The panel itself is `visible=bool(output_controls)` (`:131`), but `output_controls` is first filled from `fallback_text` (`:102-107`) — and in `assistant_view.py:1368-1370` the fallback is `live_output or outcome` (any outcome except `"(no output)"`). So a done step with **empty `outputs` but a non-empty outcome/fallback** renders the panel with text + a Copy Output button that copies nothing (`copy_output` exits at the `if not outputs` guard). The code even acknowledges it: `assistant_view.py:1338-1339` "Without it an empty-output step renders as nothing but a copy button." Rendered at `assistant_view.py:1371-1377`. |
| Shared helper | `src/components/notebook_cell/actions.py:169-220` `copy_output(page, outputs)` | Guards only `if not outputs: _snack(page, "No output to copy.")` (`:171-172`); otherwise extracts text (stream/error/execute_result `text/plain`), ANSI-strips it (`:216`) and copies if non-empty (`:218-220`). **It does not reject placeholder-only content** — an outputs list of `[{"type":"stream","text":"None"}]` copies the literal string `None`. |

### Where "None idle" comes from

The literal string `None idle` exists **nowhere** in the repo (grep over all of `src/`, `tests/`, `docs/`, and all git revisions). It is a runtime composition of two real code paths:

- **"None" as output text** — three coercion/passthrough paths produce an output entry whose text is exactly `None`:
  - `src/screens/session/notebook_view.py:429-431` `_append_output`: non-dict payload → `{"type": "stream", "text": str(text_or_dict)}` — `str(None)` == `"None"`.
  - `src/services/ai_tools.py:204-206` `_exec`'s `_on_output`: `entry = payload if isinstance(payload, dict) else {"text": str(payload)}` — same `str(None)` coercion.
  - Remote-kernel `execute_result` with `data["text/plain"] == "None"` passes through `src/services/colab/execution.py:42-55` (`_to_cell_output`) unchanged and renders as text `None` via `src/components/notebook_cell/output.py:59-101`.
- **"idle"** — the not-running state: `status_dot` docstring "gray for idle" (`src/core/styles.py:212-213`), send/stop button "send when idle, stop when busy" (`src/screens/assistant_view.py:357`), and the session status string `"IDLE"` produced at `src/services/colab/session_ops.py:327` (`"BUSY (…)" if running else "IDLE"`), shown on session cards (`src/components/session_card.py:21,33`) and the session header (`src/screens/session/__init__.py:350`).

So the owner's "None idle" = an output panel showing the placeholder text `None` (a `str(None)`-coerced or kernel `text/plain: "None"` entry) while the cell/step is idle — i.e. **there is nothing meaningful to copy, yet Copy Output is visible** (and copies the string "None", or nothing at all when `outputs == []`).

### Correct visibility rule for Copy Output

**Show the Copy Output button only when there is copyable content**, where "copyable" means the same extraction `copy_output` performs (`actions.py:174-220`): at least one output entry that yields non-empty text after joining and ANSI-stripping — i.e. gate on the *extracted* text, not merely on `bool(outputs)` and not on `cell.is_running`.

Concretely:
- `src/components/ai_step_output.py:168` — change `if page is not None:` to also require copyable content (e.g. `if page is not None and _copyable_text(outputs):`), and drop/merge the dead `elif outputs:` disabled-button branch (`:182-189`, `on_click=None` is never useful). `assistant_view.py:1368-1370` fallback text must NOT make the button appear when `outputs` is empty.
- `src/components/notebook_cell/__init__.py:329-334` — gate the Copy Output IconButton on `bool(output_controls)` (the panel already hides when idle+empty at `:367`; the remaining leak is the `or cell.is_running` clause showing the button on a running-but-empty cell — hide the button, or the whole `output_actions` row, when `output_controls` is empty).
- Optionally harden `copy_output` (`actions.py:169`) to treat a `"None"`-only/whitespace result as nothing-to-copy.
- Existing test pin: `tests/test_ai_step_outputs.py:215` asserts Copy Output is present for a done row **with** outputs — that stays green under the new rule.

---

## 4. Findings table

| # | Finding | Surface | v2.2.0 location | v2.1.2 | DDGS ref | Verdict / fix |
|---|---|---|---|---|---|---|
| 1 | Banner builder used by all screens; mobile-only, 0x0 for premium/desktop | all | `src/core/styles.py:108` | same | `DDGS core/styles.py:12` | OK — single entry point |
| 2 | `AdService.get_banner_ad` dead in production (tests only) | service | `src/services/ad_service.py:138` | `:105` | `DDGS ad_service.py:114` | F5: use or delete |
| 3 | Home: 2 inline banners (after sessions, after features) | home | `home/__init__.py:341,343` | `:325,327` | `home_screen.py:853,900` | OK, matches DDGS |
| 4 | Session selector: banner near top after CTA | sessions | `session_selector.py:86` | `:86` | n/a | OK |
| 5 | Files: banner near top after toolbar | files | `files/__init__.py:598` | `:482` | n/a | OK |
| 6 | Settings: 2 SPONSOR banner sections inline | settings | `settings/__init__.py:93,99` | `:32,36` | `settings_screen.py:160,170,178` | OK, matches DDGS |
| 7 | History: single banner at BOTTOM of scroll column — owner complaint | history | `history/__init__.py:325` | `:302` (also bottom) | `history_screen.py:274` (bottom) | **F1: move to top** of the column (files/selector pattern); alternative = keep for DDGS parity. Don't add a second one |
| 8 | History "Export as .ipynb" gated by rewarded interstitial | history | `history/__init__.py:100` | same | n/a | OK as-is; screen banner covers post-export |
| 9 | Notebook export-format dialog has NO banner | export dialog | `notebook_view.py:1083-1133` (AlertDialog `:1102`) | no dialog existed (`_export_ipynb` at v2.1.2 `:278`) | n/a | **F2: add `build_banner_ad(page)` in dialog content** |
| 10 | Notebook cells: banner every 2nd cell + bottom | notebook | `notebook_view.py:1435-1436, 1576` | `:527,548` (same semantics) | n/a | **F4: leave as-is** (owner) |
| 11 | Chat has NO per-reply or view-level banner; app-level banners live on tab screens | chat | none in `assistant_view.py` (view `:474-488`, `_render` `:1198-1216`) | none | DDGS inserts pooled banner after every AI reply (`chat_screen.py:1629-1690`, `BANNER_AD_EVERY_N_REPLIES=1` at `:51`, insert `:1685-1689`) | **F3: nothing to remove; keep absent; pin with a comment so the DDGS pattern is not ported** |
| 12 | Assistant-chats history dialog has no banner | chat history dialog | `assistant_history.py:30, ~137` | same | n/a | acceptable; not in owner's fix list |
| 13 | Copy Output shown with nothing copyable: chat step button unconditional on `page is not None`; fallback text makes panel visible with empty outputs | chat step | `ai_step_output.py:168-189` (panel visible `:131`, fallback fill `:102-107`); call `assistant_view.py:1368-1377`; comment `:1338-1339` | file didn't exist at v2.1.2 | DDGS search-step pattern is the model | **F6a: gate button on copyable extracted text** |
| 14 | Copy Output visible while cell running with zero outputs (`visible = bool(output_controls) or cell.is_running`) | notebook cell | `notebook_cell/__init__.py:367`, button `:329-334` | v2.1.2 same (`:344` visible, `:307-310` button) | n/a | **F6b: gate button on `bool(output_controls)`** |
| 15 | `copy_output` only guards `not outputs`; copies literal "None" from placeholder entries | shared helper | `actions.py:169-172, 216-220` | v2.1.2 same logic | n/a | harden: treat empty/"None"-only extracted text as nothing to copy |
| 16 | "None idle" is not a literal; = `str(None)`-coerced output entries (`notebook_view.py:429-431`, `ai_tools.py:204-206`, kernel `execute_result` `text/plain:"None"` via `execution.py:42-55`) shown while idle (`styles.py:212-213`, session `"IDLE"` at `session_ops.py:327`) | outputs | see left | — | — | explains the owner's quote; fixed by F6 visibility rule |

**One-line summary of the placement rule:** top-of-content inline banner per screen (history moves up from the bottom), banner inside the export-ipynb dialog, notebook cell banners untouched, chat replies never get their own banner (app-level tab banners already cover it), and Copy Output appears only when the ANSI-stripped extracted output text is non-empty.
