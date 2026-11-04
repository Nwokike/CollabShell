# CollabShell Research: Wake Lock, Flet Versions, and flet_ads Rewarded Usage

**Generated:** 2026-11-02  
**Project:** `/home/maikel/Desktop/kiri-apps/CollabShell`  
**Venv:** `.venv/lib/python3.14/site-packages/` (flet 1.0.4)

---

## 1. Wake Lock in Flutter/Flet 1.0.4

### 1.1 Flet's Built-in Wakelock Service

Flet 1.0.4 exposes a **`Wakelock` service** at:
- **Source:** `/home/maikel/Desktop/kiri-apps/CollabShell/.venv/lib/python3.14/site-packages/flet/controls/services/wakelock.py:7-32`
- **Exported in:** `flet/__init__.py:621, 1229, 1771`

```python
# Usage (Flet 1.0.4):
from flet import Wakelock, Page

async def main(page: Page):
    wakelock = Wakelock()
    page.services.append(wakelock)  # Auto-registered if constructed in page context
    
    await wakelock.enable()   # Keeps screen ON
    # ... app logic ...
    await wakelock.disable()  # Allows sleep again
    enabled = await wakelock.is_enabled()
```

**Implementation details:**
- `Wakelock` extends `Service` (`flet/controls/services/service.py:11-55`)
- Services auto-register with `page._services` when constructed in page context
- Methods invoke Dart-side via `_invoke_method("enable"|"disable"|"is_enabled")`

### 1.2 What Wakelock Actually Does (Flutter `wakelock_plus`)

**Local source + Pub.dev confirmation:**
- `wakelock_plus` (Flutter plugin used by Flet) **only prevents screen sleep** (`FLAG_KEEP_SCREEN_ON` on Android, equivalent on iOS/macOS/Windows/Linux/web)
- **Explicitly states:** *"it only enables the screen wakelock and not any partial (CPU) wakelocks that would keep the app alive in the background"* — [pub.dev/packages/wakelock_plus](https://pub.dev/packages/wakelock_plus)

| Platform | Behavior | Prevents Background Kill? |
|----------|----------|---------------------------|
| **Android** | Sets `FLAG_KEEP_SCREEN_ON` on Activity window | ❌ No — does not acquire `PARTIAL_WAKE_LOCK` |
| **iOS** | `UIApplication.isIdleTimerDisabled = true` | ❌ No — iOS has no CPU wakelock |
| **Desktop (Win/macOS/Linux)** | Platform-specific screen-on APIs | ❌ No — only keeps display awake |
| **Web** | Wake Lock API (`navigator.wakeLock.request('screen')`) | ❌ No — screen only |

### 1.3 Android Background Execution (Doze Mode)

**Default behavior when minimized:**
- **Doze mode** (API 23+): Defers network, jobs, alarms when device stationary & screen off
- **App Standby** (API 23+): Restricts network for unused apps
- **Background execution limits** (API 26+): Services stopped shortly after app leaves foreground
- **Result:** A minimized Flet app **will be killed** by the system unless it runs a **foreground service** with persistent notification

**To keep app alive when minimized on Android:**
1. **Foreground Service** — Required for long-running background work (see `flutter_background_service` package)
   - Requires `FOREGROUND_SERVICE_*` permissions (Android 14+)
   - Must show persistent notification
   - Battery optimization must be disabled by user
2. **WorkManager** — For deferrable, guaranteed background work
3. **Partial Wake Lock** (`PARTIAL_WAKE_LOCK` permission) — Keeps CPU running, but **not exposed by Flet**

**Flet 1.0.4 provides NO direct API for foreground services.** Would require:
- Custom platform channel (MethodChannel) to Android `Service`
- Or wait for upstream Flet to expose background execution APIs

### 1.4 Desktop (Windows/macOS/Linux) Minimized Behavior

| Platform | Default when minimized | Keep alive options |
|----------|------------------------|-------------------|
| **Windows** | App continues running (unless user closes) | `page.window.prevent_close = True` to intercept close; no background kill |
| **macOS** | App continues running (unless user quits) | Same; App Nap may throttle but not kill |
| **Linux** | Depends on WM/DE; usually continues | Same |

**Flet Window API** (`flet/controls/core/window.py`):
- `page.window.prevent_close = True` — intercept close button (line 257-262)
- `page.window.on_event` — listen for `WindowEventType.MINIMIZE`, `HIDE`, `CLOSE` (lines 17-70, 341-345)
- `page.on_app_lifecycle_state_change` — receives `AppLifecycleState.HIDE`/`PAUSE`/`DETACH` (page.py:629-634, types.py:1106-1181)

**Conclusion for CollabShell:** 
- **Wakelock service** keeps **screen on** (useful for terminal sessions, long-running tasks visible to user)
- **Does NOT prevent background kill on Android** — app will be killed in doze/standby when minimized
- **Desktop:** App stays alive by default; only dies on explicit user close

---

## 2. Version Landscape — 2026-11-02

| Package | Installed | Latest (PyPI) | Delta | Release Date | Key Changelog Highlights for CollabShell |
|---------|-----------|---------------|-------|--------------|------------------------------------------|
| **flet** | 1.0.4 | **1.0.5** | +0.0.1 | 2026-10-21 | Services stability, `Wakelock` service added, `page.on_app_lifecycle_state_change` events |
| **flet_ads** | 1.0.4 | **1.0.5** | +0.0.1 | 2026-10-21 | Google Mobile Ads SDK update; no new controls (`RewardedAd` still missing) |
| **flet_notifications** | 0.1.4 | **1.1.0.dev3** (dev) / 0.1.4 (stable) | +1.0 | 2026-10-30 (dev) / 2026-10-11 (stable) | **Major v1.1:** foreground service support (Android), scheduled notifications, badge API — **not in 0.1.4** |
| **flet_desktop** | 1.0.4 | **0.28.2** | **version mismatch** | 2025-05-10 | Client download/extract logic; `FLET_DESKTOP_FLAVOR`, `FLET_APP_ID` for Linux taskbar |
| **flet_terminal** | 0.3.9 | **0.4.2** | +0.1.3 | 2026-10-17 | Terminal search, themes, shortcuts, `MobileTerminal` composite |
| **flet_platform_assets** | 1.0.4 | **1.0.5** | +0.0.1 | 2026-10-21 | Icon/splash rendering for all platforms |
| **flet_cli** | 1.0.4 | **1.0.5** | +0.0.1 | 2026-10-21 | Build/pack commands; `--split-per-abi`, platform signing options |

**PyPI URLs:**
- flet: https://pypi.org/project/flet/
- flet_ads: https://pypi.org/project/flet-ads/
- flet_notifications: https://pypi.org/project/flet-notifications/
- flet_desktop: https://pypi.org/project/flet-desktop/
- flet_terminal: https://pypi.org/project/flet-terminal/
- flet_platform_assets: https://pypi.org/project/flet-platform-assets/
- flet_cli: https://pypi.org/project/flet-cli/

### Relevant to CollabShell
- **flet 1.0.5** — Wakelock service stabilized; consider upgrade
- **flet_notifications 1.1.0-dev** — Adds `LocalNotifications.start_foreground_service()` for Android background execution — **critical if CollabShell needs true background keep-alive**
- **flet_ads 1.0.5** — Still no `RewardedAd`; rewarded interstitial pattern unchanged

---

## 3. flet_ads 1.0.4 — Correct Rewarded Ad Usage

### 3.1 Available Controls & Events (Source: `/home/maikel/Desktop/kiri-apps/CollabShell/.venv/lib/python3.14/site-packages/flet_ads/`)

| Control | File:Line | Base | Events (from BaseAd + own) |
|---------|-----------|------|---------------------------|
| `BannerAd` | `banner_ad.py:8` | `LayoutControl, BaseAd` | `on_load`, `on_error`, `on_open`, `on_close`, `on_impression`, `on_click`, **`on_will_dismiss` (iOS only)**, **`on_paid` (allowlisted)** |
| `InterstitialAd` | `interstitial_ad.py:6` | `Service, BaseAd` | `on_load`, `on_error`, `on_open`, `on_close`, `on_impression`, `on_click`, `on_paid` — **single-use** (show() once) |
| `NativeAd` | `native_ad.py:9` | `BannerAd` | Inherits all BannerAd events + requires `factory_id` or `template_style` |
| `ConsentManager` | `consent_manager.py:14` | `Service` | Methods: `request_consent_info_update()`, `load_and_show_consent_form_if_required()`, `can_request_ads()`, `get_privacy_options_requirement_status()`, `show_privacy_options_form()`, `reset()` |

**BaseAd events** (`base_ad.py:31-67`):
```python
on_load:     Called when ad loaded successfully
on_error:    Called when ad request failed (data contains error info)
on_open:     Called when full-screen ad opens (pause animations)
on_close:    Called when full-screen ad closes (resume paused work)
on_impression: Called when impression recorded
on_click:    Called when ad clicked
on_paid:     Called when ad earned money (allowlisted accounts only)
```

**Critical: NO `on_reward` / `on_user_earned_reward` / `on_rewarded` event exists in flet_ads 1.0.4.**

### 3.2 AdMob Policy: When Is Reward Granted?

**Official AdMob documentation** ([Rewarded Ads](https://developers.google.com/admob/android/rewarded-ads), [Rewarded Interstitial](https://developers.google.com/admob/android/rewarded-interstitial)):

| Callback | Purpose | When Fired |
|----------|---------|------------|
| `onUserEarnedReward` (`OnUserEarnedRewardListener`) | **Grant reward HERE** | User **completed** the rewarded action (watched video, played playable) |
| `onAdDismissedFullScreenContent` (`FullScreenContentCallback`) | Clean up ad reference | Ad **closed for any reason** (watched, dismissed early, error) |

**Policy rule:** Reward **MUST** be granted only in `onUserEarnedReward`. Granting on `onAdDismissedFullScreenContent` (`on_close`) **violates AdMob policy** — rewards users who dismiss without watching.

**Rewarded vs Interstitial differences:**
- **Rewarded Ad:** Dedicated ad unit ID; `onUserEarnedReward` callback; user opts in to watch for reward
- **Interstitial Ad:** Different ad unit ID; **no reward callback**; shows between content; single-use in flet_ads
- **Rewarded Interstitial:** Hybrid — interstitial format but with reward callback; still needs dedicated ad unit ID

### 3.3 DDGS Pattern (Gold Standard) — `/home/maikel/Desktop/kiri-apps/DDGS/src/services/ad_service.py`

**Rewarded interstitial implementation (lines 273-324):**
```python
async def show_rewarded_interstitial(self, on_close: Callable) -> bool:
    if state.is_premium or not _HAS_ADS or not self._is_mobile():
        logger.info("No rewarded ad available - granting nothing")
        return False  # <-- NEVER calls on_close!

    self._active_rewarded_ad = fta.InterstitialAd(
        unit_id=self.interstitial_id,  # Uses INTERSTITIAL ID (no RewardedAd exists)
        on_load=lambda e: self.page.run_task(_show, e),
        on_close=lambda e: self.page.run_task(_close, e),  # Only called when ad ACTUALLY closes
        on_error=lambda e: logger.error(...),  # Does NOT call on_close on error
    )
    # ...
    return True

async def _close(e):
    self._active_rewarded_ad = None
    if asyncio.iscoroutinefunction(on_close):
        await on_close()  # Grants credits HERE — only after ad closes
    else:
        on_close()
```

**Key DDGS guarantees:**
1. **Premium/desktop/no-ads → returns `False`, NEVER calls `on_close`** (lines 305-312)
2. **Error path → logs only, NEVER calls `on_close`** (line 304-306)
3. **Only actual ad close → calls `on_close`** (lines 293-300)
4. Uses **interstitial ad unit ID** (no `RewardedAd` control exists in flet_ads)

### 3.4 CollabShell Divergence — `/home/maikel/Desktop/kiri-apps/CollabShell/src/services/ad_service.py:273-324`

**Current CollabShell code (AUDIT-03 #1, #10):**
```python
async def show_rewarded_interstitial(self, on_close: Callable) -> bool:
    if state.is_premium or not _HAS_ADS or not self._is_mobile():
        logger.info("No rewarded ad available - granting nothing")
        # BUG: Still calls on_close for premium/desktop/no-ads!
        if asyncio.iscoroutinefunction(on_close):
            await on_close()  # <-- GRANTS CREDITS WITHOUT AD!
        else:
            on_close()
        return False

    # ... creates ad ...
    except (...):
        logger.exception("Failed to trigger rewarded interstitial")
        # BUG: Calls on_close on ERROR too!
        if asyncio.iscoroutinefunction(on_close):
            await on_close()  # <-- GRANTS CREDITS ON ERROR!
        else:
            on_close()
        return False
```

**Wallet dialog calls this** (`wallet_dialog.py:153-174`):
```python
granted = {"ok": False}
def _on_reward(_ok=True):
    granted["ok"] = bool(_ok)  # Becomes True even when returning False!

await ad_service.show_rewarded_interstitial(_on_reward)
if granted["ok"]:
    await _on_watch_success()  # Grants credits!
```

**Violations:**
1. **Grants credits to premium users** (no ad shown)
2. **Grants credits on desktop/web** (no ad possible)
3. **Grants credits on error** (network failure, load failure)
4. **Uses interstitial ad unit ID** for "rewarded" — no `RewardedAd` control exists

**AdMob policy risk:** This implementation **will over-grant rewards** and could trigger policy violations / account suspension.

### 3.5 Ad Unit ID Configuration Per Platform

| Platform | Banner Test ID | Interstitial Test ID | Production IDs |
|----------|----------------|----------------------|----------------|
| **Android** | `ca-app-pub-3940256099942544/9214589741` | `ca-app-pub-3940256099942544/1033173712` | App-specific (DDGS: `ca-app-pub-5679949845754640/...`) |
| **iOS** | `ca-app-pub-3940256099942544/2435281174` | `ca-app-pub-3940256099942544/4411468910` | App-specific |
| **Desktop/Web** | ❌ Not supported (raises `FletUnsupportedPlatformException`) | ❌ Not supported | N/A |

**Source:** `flet_ads/base_ad.py:69-75` — `before_update()` raises on non-mobile:
```python
def before_update(self):
    super().before_update()
    if self.page.web or not self.page.platform.is_mobile():
        raise ft.FletUnsupportedPlatformException(
            f"{self.__class__.__name__} is only supported on Mobile (Android and iOS)"
        )
```

---

## 4. Recommendations

### 4.1 Wake Lock / Background Keep-Alive

| Requirement | Solution | Effort |
|-------------|----------|--------|
| **Keep screen on during active use** (terminal, long tasks) | Use `Wakelock` service: `wakelock = Wakelock(); page.services.append(wakelock); await wakelock.enable()` | Low — built into flet 1.0.4 |
| **Prevent Android kill when minimized** | **Not possible with current Flet APIs.** Options:<br>1. Wait for `flet_notifications 1.1.0` foreground service support<br>2. Custom platform channel to Android `ForegroundService` (MethodChannel)<br>3. Accept that minimized app may be killed by doze | High — requires native Android work |
| **Desktop: prevent close on minimize** | Already default behavior. Use `page.window.prevent_close = True` + `on_event` handler if confirmation needed | Low |

**Immediate action for CollabShell:**
```python
# In main.py or app entry:
from flet import Wakelock

async def main(page: Page):
    wakelock = Wakelock()
    page.services.append(wakelock)
    await wakelock.enable()  # Keep screen on for terminal sessions
    
    # Handle lifecycle for visibility-aware rendering
    page.on_app_lifecycle_state_change = lambda e: handle_lifecycle(e.state)
```

### 4.2 Version Upgrades

| Package | Current | Target | Priority | Notes |
|---------|---------|--------|----------|-------|
| `flet` | 1.0.4 | **1.0.5** | High | Wakelock stabilized, lifecycle events |
| `flet_ads` | 1.0.4 | **1.0.5** | Medium | Google Mobile Ads SDK update |
| `flet_notifications` | 0.1.4 | **1.1.0** (when stable) | **Critical if background needed** | Adds `start_foreground_service()` for Android keep-alive |
| `flet_terminal` | 0.3.9 | **0.4.2** | Medium | Search, themes, shortcuts |
| `flet_cli` | 1.0.4 | **1.0.5** | Low | Build improvements |

**Note on `flet_desktop`:** Installed 1.0.4 vs PyPI latest 0.28.2 — version scheme differs. Current version works with flet 1.0.4; upgrade with flet.

### 4.3 Fix flet_ads Rewarded Usage (CRITICAL)

**Must fix before production — AdMob policy violation risk.**

**Option A: Align with DDGS (Recommended)**
```python
# In ad_service.py — show_rewarded_interstitial:
async def show_rewarded_interstitial(self, on_close: Callable) -> bool:
    if state.is_premium or not _HAS_ADS or not self._is_mobile():
        logger.info("No rewarded ad available - granting nothing")
        return False  # <-- REMOVE on_close call entirely
    
    try:
        self._active_rewarded_ad = fta.InterstitialAd(
            unit_id=self.interstitial_id,
            on_load=lambda e: self.page.run_task(_show, e),
            on_close=lambda e: self.page.run_task(_close, e),  # Only on actual close
            on_error=lambda e: logger.error("Rewarded interstitial error: %s", e.data),  # NO on_close
        )
        # ...
        return True
    except Exception:
        logger.exception("Failed to trigger rewarded interstitial")
        return False  # <-- NO on_close call on error
```

**Option B: Wait for `RewardedAd` control** (not in flet_ads 1.0.5 either)
- Track upstream: https://github.com/flet-dev/flet/issues
- Implement server-side reward verification as fallback

**Option C: Remove rewarded ads entirely** until proper `RewardedAd` exists
- Use interstitial ads only for non-rewarded monetization
- Premium-only credits via purchase

### 4.4 AdMob Compliance Checklist

- [ ] **Never grant reward on `on_close`** — only on verified completion (requires `RewardedAd` control)
- [ ] **Use separate ad unit IDs** for banner / interstitial / rewarded (when available)
- [ ] **Test with test IDs** during development (`USE_TEST_IDS = True`)
- [ ] **Implement server-side reward validation** for production (receipt verification)
- [ ] **Respect `on_error`** — do not grant reward on load/show failure
- [ ] **Premium users never see ads** — gate all ad methods with `state.is_premium`

### 4.5 DDGS Parity Items (from audit-03 + ref-01)

| # | Fix | Location | Reference |
|---|-----|----------|-----------|
| 1 | Remove `on_close` call when returning `False` in `show_rewarded_interstitial` | `ad_service.py:305-312` | DDGS line 305-312 |
| 2 | Remove HTTP 400 from `status_refusal` | `license_service.py:73-81` | DDGS excludes 400 |
| 3 | Add `"active"` to `_STATUS_COPY` | `premium_section.py:46-50` | DDGS has explicit entry |
| 4 | Use `page_has_ads()` helper in `_notify_premium_unlocked` | `premium_service.py:241-255` | DDGS pattern |
| 5 | Move `core.tokens` import to module top / use hardcoded 320x50 | `ad_service.py:143-150` | DDGS uses constants |
| 6 | Reset `_PRICES_ATTEMPTED = False` on catalog fetch failure | `premium_section.py:299-301` | DDGS line 176 |
| 7 | Stamp `_last_reconcile_at` on all early returns | `premium_service.py:111-112` | DDGS `finally` block |

---

## Appendix: Key Source References

| Topic | File:Line |
|-------|-----------|
| Flet Wakelock service | `.venv/lib/python3.14/site-packages/flet/controls/services/wakelock.py:7-32` |
| Service base class | `.venv/lib/python3.14/site-packages/flet/controls/services/service.py:11-55` |
| Page lifecycle events | `.venv/lib/python3.14/site-packages/flet/controls/page.py:629-634, 880-886` |
| AppLifecycleState enum | `.venv/lib/python3.14/site-packages/flet/controls/types.py:1106-1181` |
| Window API (minimize, prevent_close) | `.venv/lib/python3.14/site-packages/flet/controls/core/window.py:17-70, 257-262, 341-345` |
| flet_ads BaseAd events | `.venv/lib/python3.14/site-packages/flet_ads/base_ad.py:31-67` |
| flet_ads InterstitialAd (single-use) | `.venv/lib/python3.14/site-packages/flet_ads/interstitial_ad.py:6-37` |
| flet_ads platform restriction | `.venv/lib/python3.14/site-packages/flet_ads/base_ad.py:69-75` |
| DDGS ad_service rewarded | `/home/maikel/Desktop/kiri-apps/DDGS/src/services/ad_service.py:273-324` |
| DDGS ad_service interstitial | `/home/maikel/Desktop/kiri-apps/DDGS/src/services/ad_service.py:146-218` |
| CollabShell ad_service | `/home/maikel/Desktop/kiri-apps/CollabShell/src/services/ad_service.py:273-324` |
| CollabShell wallet_dialog | `/home/maikel/Desktop/kiri-apps/CollabShell/src/components/wallet_dialog.py:153-174` |

---

**End of Research Document**