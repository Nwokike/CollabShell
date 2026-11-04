# Investigate 05 — tab-entry refresh regression

## Root cause (no-refresh after leaving the assistant)
2.2.0 put the assistant on its own `page.views` entry (`assistant_view.py:1668-1683`,
close at 614-631; main.py:471-479,919-929). Closing it changes NO shell state
(`assistant_open` is written but never read by the shell), so `HomeScreen`
(same fn + same key `home_tab`) is reconciled in place — no remount — and home's
`use_effect` deps are only `[is_online, is_authenticated]` (`home/__init__.py:53-60`),
so `_load_sessions` never re-runs. Home also renders a LOCAL `sessions` use_state
copy (lines 28,146,183), so even `state.active_sessions` writes wouldn't repaint it.
v2.1.2 had no assistant; every return went through subview/tab state → remount →
mount effect. NOT caused by the page.update() removals.

Tab ENTRY itself refreshes home (remount fires the mount effect). Notebooks/terminal/
files selector tabs NEVER fetch on entry in any version (`session_selector.py` has no
load effect; renders `state.active_sessions` only).

## Fix design
1. Home: add `state.assistant_open` (+ `active_subview`) to the load effect deps AND
   render from observable `state.active_sessions` (keep local state only for
   loading/error flags).
2. Central shell effect in app_shell.py keyed on `[current_tab, active_subview,
   assistant_open]` calling a new `ControllerMethods.refresh_sessions` (main.py) that
   re-lists into `state.active_sessions` — covers all four tabs.
3. SessionSelectorTab: own `use_effect(..., [mode])` that re-lists on entry.
4. Parity: assistant `stop_session` tool must update `state.active_sessions` like
   `create_session` does (ai_tools.py:624).

## Findings
| # | Finding | Location |
|---|---|---|
| 1 | home load effect deps miss assistant/subview | home/__init__.py:53-60 |
| 2 | home renders local copy, not the observable | home/__init__.py:28,146,183 |
| 3 | tab switch = key-based remount (object_patch.py:1461-1468) | app_shell.py:644-663 |
| 4 | assistant = raw view push/pop; assistant_open unread by shell | assistant_view.py:1668-1683,614-631; core/state.py:130 |
| 5 | selector tabs never fetch on entry (both versions) | session_selector.py:14-93 |
| 6 | ai stop_session doesn't update active_sessions | ai_tools.py ~677 |
