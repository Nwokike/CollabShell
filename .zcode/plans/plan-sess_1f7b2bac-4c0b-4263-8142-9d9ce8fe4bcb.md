## Adopt flet 0.86.5 APIs

### A. Replace DNS-probe polling with native `ft.Connectivity`

**`src/main.py`**
- Import `ConnectivityType` from flet.
- After creating `ad_service`, register a connectivity service:
  ```python
  state.connectivity = ft.Connectivity(on_change=_on_connectivity_change)
  page.services.append(state.connectivity)
  ```
- `_on_connectivity_change(e)`: `state.is_online = ConnectivityType.NONE not in e.connectivity`; if `page.route == "/home"` rebuild the view (replaces the poll's banner-refresh trigger).
- `_initial_route()`: replace `probe_connectivity()` with `state.connectivity.get_connectivity()` → `state.is_online = ConnectivityType.NONE not in types`.
- Delete the `_periodic_connectivity_check` loop (no longer needed).

**`src/core/router.py`**
- Offline retry: replace `probe_connectivity()` with `state.connectivity.get_connectivity()`.
- Remove `from core.connectivity import probe_connectivity`.

**Delete `src/core/connectivity.py`** — dead code (per delete-dead-code preference).

### B. SnackBar improvements (`src/main.py`)
- `_snack()`: add `behavior=ft.SnackBarBehavior.FLOATING`, `dismiss_direction=ft.DismissDirection.UP`.
- `on_error`: add `persist=True`, `show_close_icon=True`.

### C. `is_mobile()` cleanup
- `views/history_view.py:108` → `page.platform.is_mobile()`
- `views/session/ipynb.py:12` → `page.platform.is_mobile()`
- `views/files/actions.py:130` → `page.platform.is_mobile()`

### Net effect
- Reactive, battery-friendly connectivity (native event vs 12s DNS poll).
- Snackbars float over the nav bar; errors persist until dismissed.
- Cleaner platform checks. No behavioral regression.