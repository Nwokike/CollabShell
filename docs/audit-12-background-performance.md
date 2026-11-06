# Audit 12: Background Tasks & Performance Audit (Delta since v2.1.2)

Audit date: 2026-11-06  
Scope: All background services, loops, keep-alive routines, and schedulers running in CollabShell since v2.1.2.

---

## 1. Summary of Background Tasks

| Task / Service | Module | Interval / Trigger | CPU / Battery Impact | Safety / Cancellation |
|---|---|---|---|---|
| **SessionKeepAlive** | `services.colab.keepalive` | 240.0s | ~0% (single `pass` kernel eval every 4 min) | Catches `asyncio.CancelledError`, logs warnings on failure, re-syncs sessions |
| **CreditService Sweep** | `services.credit_service` | 60.0s | ~0% (in-memory hold age filter) | Handles `CancelledError`, releases orphan holds stranded by crashed turns |
| **RouterStatusWatchdog** | `services.router_watchdog` | 3.0s fg / 30.0s bg | Minimal (<0.1%) | Uses `PROBE_MISS_TTL`, switches to 30s in bg via lifecycle, notifies only on state transitions |
| **PremiumService Reconcile** | `services.premium_service` | 3600.0s (1 hr) | 0% | Hourly tick, resume debounced to 60s, checkout watcher capped at 10m |
| **StorageService Flush** | `services.storage_service` | Event-driven (0.2s debounce) | Zero disk thrash | In-memory read, debounced atomic tmp-file replace write |
| **SessionNotificationService** | `services.session_notify` | Event-driven | Zero polling | FGS lifecycle tied to active session |

---

## 2. Detailed Findings & Optimizations

### 2.1 Keep-Alive Engine (`SessionKeepAlive`)
- **Finding**: PR #144 in `google-colab-cli` eliminated client-side ping keep-alives. Colab idle-prunes VMs after ~7-8 minutes of kernel inactivity. WebSocket pings alone do not reset this timer.
- **Verification**: `SessionKeepAlive` executes `pass` via `exec_code` every 240s (well under the 7-8 minute prune mark).
- **Failure Resilience**: If an execution fails (e.g. temporary connection blip), failure counter increments, session list re-syncs, and it never crashes the application loop.

### 2.2 Router Status Watchdog & Lifecycle
- **Finding**: The watchdog polled ports 8082..8092 every 3s in the foreground, but previously had no bridge from `_on_lifecycle_change` to activate its background throttling.
- **Optimization**: Added `self.router_watchdog.set_background(True)` on app pause/hide/detach, and `False` on resume. When backgrounded, watchdog interval scales from 3s to 30s (`ROUTER_STATUS_INTERVAL_BG_S`), preventing battery drain on Android devices.

### 2.3 Credit Economy & Storage Parity
- **Finding**: In-memory credit tracking previously allowed restarting the app to restore 50 credits, violating the daily cap policy.
- **Resolution**: Ported persistent storage architecture from DDGS (`STORAGE_CREDITS`, `STORAGE_LAST_RESET`).
- **Performance**: Reads are cached in-memory under an `asyncio.Lock`. Writes are debounced through `StorageService` (0.2s window), avoiding disk I/O on rapid credit mutations. Daily reset check memoizes `_reset_day` to bypass storage round-trips on hot-path balance queries.

### 2.4 Destroyed Session Safety (`_safe_run_task`)
- **Finding**: On page teardown or navigation away from active views, background callbacks calling `page.run_task` raised `RuntimeError: An attempt to fetch destroyed session`.
- **Resolution**: Wrapped in `_safe_run_task` in `src/main.py`, logging at debug level and skipping orphaned tasks cleanly.
