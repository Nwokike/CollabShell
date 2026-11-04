# Investigate 01 — FAB overlap + disappearing bottom navigation

## 1. FAB overlap (assistant FAB vs session options FAB)

Both effects write the SAME slot, `page.views[0].floating_action_button`:
- `_sync_assistant_fab` (app_shell.py:~210-260) — assistant FAB; deps include
  `active_subview`; it claims the slot when "no FAB that isn't ours" is present,
  and skips (`current is not None -> return`) when the session's FAB is mounted.
- `_sync_fab` (screens/session/__init__.py:~279) — session options FAB; writes the
  slot whenever the session screen renders.

Owner's rule: on the bottom-nav tabs (home, notebooks list, terminal list, files,
settings) the slot must hold the ASSISTANT FAB; inside a session subview
(notebook/terminal/files) it must hold the OPTIONS FAB — never both, never neither.

Why they fight today: the "who owns the slot" decision is inferred from control
identity (`current is _assistant_fab_ref.current`) instead of from state, and both
effects run on overlapping dep sets. A stale session FAB (or a stale assistant FAB
after leaving a session) blocks or double-claims the slot depending on render
order, which shows up as overlap/guessed behavior.

Fix design (deterministic ownership):
- `_sync_assistant_fab`: claim the slot ONLY when `not state.active_subview`
  (and app_ready/onboarding_done); CLEAR it whenever `state.active_subview` is set
  — do not infer from control identity.
- `_sync_fab`: write the slot ONLY when `state.active_subview == "session"`;
  clear otherwise. Both effects keep their deps; ownership becomes a pure
  function of `active_subview`, so render order cannot produce overlap.
- On leaving a session, the assistant effect re-claims (deps already include
  `active_subview`); on entering, the session effect claims.

## 2. Bottom navigation disappearing (regression vs 2.1.2)

`_sync_navigation_bar` (app_shell.py:139-195) hides the bar when
`not app_ready or not onboarding_done or not is_authenticated or active_subview`.
v2.1.2 did the same assignments BUT followed each with `page.update()`
(`git show v2.1.2:src/app_shell.py` lines ~96-98 and ~118-127). In 2.2.0 those
`page.update()` calls were removed as a flet-lifecycle violation — after which the
`navigation_bar = None` (or the rebuilt bar) is assigned inside the effect
callback but never painted, so the bar visually vanishes on opening a subview and
only returns when something else forces a page update (theme toggle).

The owner wants the bottom navigation to NOT disappear when opening pages at all.

Fix design:
- Stop hiding the bar for `active_subview` — keep it visible on every screen
  (only hide while loading/onboarding/unauthenticated, as 2.1.2 effectively did
  visually). This alone removes the disappearing-when-opening-page complaint.
- Make the assignment reliable under flet 1.1: either compute the NavigationBar
  in the component body (reactive, no effect needed) or keep the effect but give
  it a safe post-render repaint mechanism. Never mutate a mounted control during
  render (flet 1.1 frozen-controls rule).
