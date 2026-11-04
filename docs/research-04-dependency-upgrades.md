# Research: dependency upgrades to latest (2026-11-02) — additions & improvements to implement

Owner decision: bump ALL dependencies to latest and utilize them fully. Source: pyproject.toml +
uv.lock + PyPI/GitHub as of 2026-11-02. Generated during plan mode from the Explore agent report.

> Correction to audit-07: Python **3.14.9 exists** (uv-managed; the `.venv` runs cpython-3.14).
> Do NOT "fix" 3.14→3.13. System python is 3.15; CI `UV_PYTHON: 3.14` is valid.

## 1. Version table (installed → latest → risk)

| Package | Installed | Latest 2026-11-02 | Risk | URL |
|---|---|---|---|---|
| flet | 1.0.4 | **1.0.5** | minor (FastAPI 0.145+ fix; wakelock stabilized) | pypi.org/project/flet/1.0.5/ |
| flet-ads | 1.0.4 | **1.0.5** | minor (Mobile Ads SDK bump; still NO RewardedAd/on_reward) | pypi.org/project/flet-ads/ |
| flet-cli | 1.0.4 | **1.0.5** | minor (build/pack improvements) | pypi.org/project/flet-cli/ |
| flet-desktop | 1.0.4 | align with flet 1.0.5 line | minor (build-time only) | pypi.org/project/flet-desktop/ |
| flet-platform-assets | 1.0.4 | **1.0.5** | none | pypi.org/project/flet-platform-assets/ |
| flet-terminal | 0.3.9 | **0.4.2** | minor; new features below | pypi.org/project/flet-terminal/0.4.2/ |
| google-colab-cli | 0.7.4 | **0.7.5** | none (maintenance re-tag; PR #136/#144 already in 0.7.4) | pypi.org/project/google-colab-cli/ |
| pydantic | 2.14.1 | **2.14.2** | none | pypi.org/project/pydantic/ |
| pillow | 12.3.0 | **13.0.0** | minor | pypi.org/project/pillow/ |
| tornado | 6.5.10 | **6.6** | minor | pypi.org/project/tornado/ |
| jupyter-kernel-client | 0.9.0 | 0.15.0 max | **PIN `<1.0`** (1.0 renamed JupyterSubprotocol→JupyterKernelClient; colab_cli incompatible) | |
| openai | 2.54.0 | 3.42.1 | **PIN `<3.0`** (kani 1.10 doesn't support 3.x Responses client) | |
| watchdog | 6.0.0 | 7.0.0 | **breaking if adopted** (pattern `**/*.py`, attrib events); app doesn't use it yet | |
| httpx, rich, kani[openai] 1.10.0, jupyter-client 8.10.0, jupyter-core, nbformat, pyzmq, tiktoken, cryptography, qrcode, requests | — | already latest | none | |

## 2. flet-terminal 0.4.2 new capabilities → implement in `src/screens/session/terminal_panel.py`
- Built-in search: `MobileTerminal.search()` / `TerminalSearchBar` (replaces custom `_toggle_search`)
- `ExtraKeysBar` on-screen toolbar (Esc/Tab/Ctrl/Alt/arrows, sticky modifiers) — mobile UX
- Expanded `BUILTIN_THEMES` + `set_theme()` (Dracula, GitHub Dark, Monokai, Solarized, …)
- Standardized `on_shortcut` names (new_terminal, close_terminal, switch_terminal_N, prev/next, toggle_search, clear, copy, paste, zoom_*, help) — verify mapping in `_handle_shortcut`
- `copy_selection_async()` / `paste()` / `clear_selection()` instead of manual `ft.Clipboard()`
- `zoom_in/out/reset`, `font_size`, `toggle_cursor_blink()`; DataChannel `send_bytes()`

## 3. Other "utilize fully" backlog (capability → target file)
- `ft.Wakelock` (flet 1.0.4/1.0.5, `flet/controls/services/wakelock.py`): register in `src/main.py`, enable during active session, disable on background/close. Foreground service: research only (ships with Flet 1.1.0 notifications — NO notification code now).
- kani 1.10.0 unexposed options (`dep-04`): `desired_response_tokens`, `always_included_messages`, `retry_attempts`, `AIFunction.auto_retry/enabled/after`, `OpenAIEngine.api_type` per model from router catalog, `hyperparams` (temperature/top_p/stop/…) exposed in Settings, `Kani.save/load`.
- nbformat/jupyter (`dep-05`): `nbformat.validate()` in `ipynb_converter.py`; preserve cell `execution_count`/`id`; handle `update_display_data`/`clear_output`; render all MIME types in `notebook_cell/output.py`; `_join_text` for list streams; preserve `transient.display_id` in `execution.py`.
- tornado: native `ping_interval`/`ping_timeout` + close-code classification in `terminal_client.py`; `requests.post` → shared `httpx.AsyncClient`.
- rich: `Color.from_ansi()` in `ansi_parser.py`, configurable span cap.
- flet_ads: still no `RewardedAd`/`on_reward` in 1.0.5 — fix `ad_service.show_rewarded_interstitial` per DDGS (grant only on real ad close after `on_open`/`on_impression`; never on no-show/error paths).
- colab-cli 0.7.5: no functional delta; keep-alive is app-side (`keepalive.py` executing `pass`/kernel_info every ~4 min — backend idle-prunes after ~7–8 min of no kernel activity).

## 4. Upgrade commands (implementation)
```bash
uv lock --upgrade-package flet --upgrade-package flet-ads --upgrade-package flet-cli \
  --upgrade-package flet-platform-assets --upgrade-package flet-terminal \
  --upgrade-package google-colab-cli --upgrade-package pydantic --upgrade-package pillow \
  --upgrade-package tornado
# keep pins: jupyter-kernel-client>=0.15.0,<1.0 ; openai>=2.54.0,<3.0 ; watchdog<7 if adopted
```
Then `uv sync`, `ruff check`, full `pytest`.
