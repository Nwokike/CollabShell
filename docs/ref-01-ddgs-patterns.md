# DDGS Reference Patterns — What CollabShell Was Supposed to Learn

Extracted from `/home/maikel/Desktop/kiri-apps/DDGS/src/` (gold standard). Cross-referenced with CollabShell HEAD (76a9d4b) and audit findings in `docs/audit-03-ads-premium-license.md`.

---

## 1. Ads Service Patterns

### 1.1 Ad Unit IDs per Platform (Production vs Test)

**DDGS** (`src/services/ad_service.py:35-62`):
```python
USE_TEST_IDS = False  # Production AdMob IDs active

BANNER_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/9214589741"
INTERSTITIAL_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/1033173712"

BANNER_ID_ANDROID_PROD = "ca-app-pub-5679949845754640/9885079510"
INTERSTITIAL_ID_ANDROID_PROD = "ca-app-pub-5679949845754640/5339329844"

@property
def banner_id(self) -> str:
    if self.USE_TEST_IDS:
        return self.BANNER_ID_ANDROID_TEST
    return self.BANNER_ID_ANDROID_PROD

@property
def interstitial_id(self) -> str:
    if self.USE_TEST_IDS:
        return self.INTERSTITIAL_ID_ANDROID_TEST
    return self.INTERSTITIAL_ID_ANDROID_PROD
```

**WHY**: Single source of truth per platform; `USE_TEST_IDS` flip is the only thing that changes between test/prod. No iOS IDs (DDGS is Android-first; iOS would be added per-platform).

**CollabShell gap** (`src/services/ad_service.py:35-71`):
- Has `NATIVE_ID_ANDROID_PROD` and `NATIVE_ID_ANDROID_TEST` that DDGS doesn't — dead code for a native ad format DDGS removed
- `banner_id` / `interstitial_id` properties exist but CollabShell's `get_banner_ad` uses `tokens.BANNER_WIDTH/HEIGHT` (see §1.5)
- **Audit-03 #5**: `get_banner_ad` imports `core.tokens` at runtime inside the `try` block — on desktop/web, `fta.BannerAd` constructor raises `FletUnsupportedPlatformException` **before** the import executes, making the pattern fragile

**Adopt this first**: Move banner dimensions to constants (320x50 like DDGS) and remove native ad IDs.

---

### 1.2 60-Second Interstitial Cooldown

**DDGS** (`src/services/ad_service.py:31, 234-236, 246-248`):
```python
MIN_INTERSTITIAL_GAP = 60.0  # seconds between interstitials (all call sites)

# In show_interstitial():
now = time.time()
if now - state.last_interstitial_ts < self.MIN_INTERSTITIAL_GAP:
    return False
# ...
state.last_interstitial_ts = now  # Stamped ONLY when ad actually shows
```

**WHY**: The cooldown is enforced at the **show** moment, not at the queue/load moment. `_show_loaded` (line 219) stamps the timestamp only when `interstitial.show()` succeeds — a failed show leaves the gap unspent so the next trigger can try again.

**CollabShell gap** (`src/services/ad_service.py:241-292`):
- Logic is similar but `show_interstitial` returns `True` when `_pending_interstitial` is set (line 280-282) — caller may think an ad was shown when it's only queued
- **Audit-03 #12**: Return value semantics confusing — `True` means "ad shown OR queued", not "ad shown"

**Adopt this first**: Document return value clearly; ensure timestamp stamps only on successful show (DDGS already does this correctly in both).

---

### 1.3 Double-Click / Double-Trigger Prevention

**DDGS** (`src/services/ad_service.py:237-242, 259-269`):
```python
# In _handle_loaded:
if self._pending_interstitial:
    self._pending_interstitial = False
    self.page.run_task(self._show_loaded)

# In show_interstitial:
if self._pending_interstitial:
    # Already queued by an earlier trigger; its show stamps the gap.
    return True
# Queue a fresh load...
self._pending_interstitial = True
```

**WHY**: `_pending_interstitial` flag prevents multiple rapid calls from creating multiple interstitial loads. The first trigger sets the flag; subsequent triggers return `True` immediately (ad is "queued"). When the ad loads, `_handle_loaded` clears the flag and shows it.

**CollabShell gap**: Same pattern exists (`src/services/ad_service.py:260-290`) — this one is **correctly ported**.

---

### 1.4 Premium Exemption (No Ads for Premium Users)

**DDGS** (`src/services/ad_service.py:116-122, 149-155, 228-233, 283-286, 305-312`):
```python
# Every public method gates on state.is_premium FIRST:
if state.is_premium or not _HAS_ADS or not self._is_mobile() or not self._can_request_ads:
    return ft.Container(width=0, height=0)  # banner
    return False  # interstitial
    return False  # rewarded interstitial (NO on_close call!)
```

**Critical DDGS behavior** (`src/services/ad_service.py:305-312`):
```python
if state.is_premium or not _HAS_ADS or not self._is_mobile():
    logger.info("No rewarded ad available - granting nothing")
    return False  # <-- NO on_close call!
```

**WHY**: Premium users never see ads, never trigger ad loads, and **never get rewarded credits via `on_close` callback**. The `on_close` is only called when an ad actually closes (line 211-218 for interstitial, line 293-300 for rewarded).

**CollabShell gap — CRITICAL** (`src/services/ad_service.py:305-312`, **Audit-03 #1**):
```python
if state.is_premium or not _HAS_ADS or not self._is_mobile():
    logger.info("No rewarded ad available - granting nothing")
    # Desktop/no-ads fallback: still call on_close so the UI flow continues
    if asyncio.iscoroutinefunction(on_close):
        await on_close()
    else:
        on_close()
    return False
```

CollabShell **calls `on_close` (which grants credits) for premium users, when flet_ads is missing, and on mobile web**. The comment even acknowledges the bug: *"It used to call on_close anyway… so credits were handed out for an impression nobody saw: two every 30 seconds against a 200/day cap"*. But the code **still does it**.

**CollabShell wallet_dialog.py** (`src/components/wallet_dialog.py:153-174`):
```python
granted = {"ok": False}
def _on_reward(_ok=True):
    granted["ok"] = bool(_ok)
await ad_service.show_rewarded_interstitial(_on_reward)
if granted["ok"]:
    await _on_watch_success()  # grants credits
```

Since `show_rewarded_interstitial` calls `on_close(True)` even when returning `False`, `granted["ok"]` becomes `True` and credits are granted.

**Adopt this first**: Remove the `on_close` call entirely when returning `False` — exactly as DDGS does.

---

### 1.5 Banner Ad Dimensions (Hardcoded vs Token Import)

**DDGS** (`src/services/ad_service.py:124-128`):
```python
ad = fta.BannerAd(
    unit_id=self.banner_id,
    width=320,
    height=50,
    on_error=lambda e: None,
)
```

**CollabShell gap** (`src/services/ad_service.py:143-150`, **Audit-03 #5**):
```python
from core import tokens  # Runtime import INSIDE try block
ad = fta.BannerAd(
    unit_id=self.banner_id,
    width=tokens.BANNER_WIDTH,
    height=tokens.BANNER_HEIGHT,
    ...
)
```

On desktop/web, `fta.BannerAd` constructor raises `FletUnsupportedPlatformException` **before** the import executes — the import is inside the `try` so it works by accident but is fragile.

**Adopt this first**: Use hardcoded 320x50 like DDGS; remove `core.tokens` dependency from ad service.

---

### 1.6 Rewarded Interstitial — "Reward Granted Only When Ad Actually Closed"

**DDGS** (`src/services/ad_service.py:273-324`):
- Creates a **separate** `InterstitialAd` instance for rewarded (not the preloaded one)
- `on_load` → shows immediately
- `on_close` → calls `on_close` callback **only after ad closes**
- `on_error` → logs error, does NOT call `on_close`
- Returns `True` when ad is triggered, `False` when unavailable (premium, no flet_ads, desktop)

**CollabShell gap**: Same structure but **calls `on_close` on error path too** (line 346-350):
```python
except (...):
    logger.exception("Failed to trigger rewarded interstitial")
    if asyncio.iscoroutinefunction(on_close):
        await on_close()  # BUG: grants credits on error
    else:
        on_close()
    return False
```

**Adopt this first**: Never call `on_close` on error — only on actual ad close.

---

### 1.7 Consent Management (UMP)

**DDGS** (`src/services/ad_service.py:79-110`):
```python
async def gather_consent(self):
    if state.is_premium or not _HAS_ADS or not self._is_mobile():
        self._can_request_ads = True
        return
    self._consent_manager = fta.ConsentManager()
    if self._consent_manager not in self.page.services:
        self.page.services.append(self._consent_manager)
    await self._consent_manager.request_consent_info_update()
    await self._consent_manager.load_and_show_consent_form_if_required()
    self._can_request_ads = await self._consent_manager.can_request_ads()
```

**WHY**: Consent only requested on mobile, non-premium. ConsentManager kept in `page.services` to prevent GC unregistration (Sherlock pattern). `_can_request_ads` gates all ad methods.

**CollabShell**: Nearly identical (`src/services/ad_service.py:98-116`) — correctly ported.

---

## 2. Premium Card Patterns (4-Row Card)

### 2.1 Card Structure — Exactly Four Rows

**DDGS** (`src/components/settings/sections_premium.py:188-594`):
```
Row 1: STATUS — always present
  - Active: "DDGS Premium" + token dates + check icon
  - Lapse (grace/expired/revoked): explains why + error icon
  - Free: pitch ("Removes ads and raises credits...") + circle icon
Row 2: PLANS — monthly/yearly/lifetime with live prices from Worker
Row 3: RECOVERY ID — shown if exists, with Copy button
Row 4: RESTORE PURCHASES — always present when license_ok
```

**WHY**: KTV Player's proven shape. A settings card that lists every field it will ever need is a form, not a menu. Typing happens in dialogs that only exist once you ask.

**CollabShell gap** (`src/screens/settings/premium_section.py:181-339`):
- Same four-row structure — **correctly ported**
- **BUT**: `_STATUS_COPY` missing `"active"` entry (**Audit-03 #3**):
```python
# DDGS (lines 51-56):
_STATUS_COPY = {
    "active": ("Premium active", "Everything Premium includes is switched on"),
    "grace": ("Payment overdue", "Finish your payment to keep Premium"),
    "expired": ("Premium expired", "Renew to switch Premium back on"),
    "revoked": ("Premium refunded", "A refund turned Premium off"),
}

# CollabShell (lines 46-50):
_STATUS_COPY = {
    "grace": ("Payment overdue", "Finish your payment to keep Premium"),
    "expired": ("Premium expired", "Renew to switch Premium back on"),
    "revoked": ("Premium refunded", "A refund turned Premium off"),
    # "active" MISSING!
}
```
Without `"active"`, the status row logic at line 184 (`if is_premium and lapse in _STATUS_COPY`) doesn't match active subscribers — they fall through to `elif is_premium` which works, BUT if `license_status` is empty string on first load (before `_recompute_premium` runs), the `else` branch shows the free pitch to a paying user.

**Adopt this first**: Add `"active"` entry to `_STATUS_COPY` and ensure first branch catches it.

---

### 2.2 Pricing — Live from Worker Catalog, Never Hardcoded

**DDGS** (`src/components/settings/sections_premium.py:58-64, 160-185`):
```python
# Plans defined by ID only; price comes from state.license_prices
_PLANS = (
    ("monthly", "Renews monthly, cancel any time"),
    ("yearly", "Two months free versus monthly"),
    ("lifetime", "Pay once, keep it"),
)

# One catalog fetch per launch, not one per repaint
_prices_attempted = False

async def _load() -> None:
    global _prices_attempted
    try:
        products = await premium.kiri_catalog(force=True)
    except Exception:
        _prices_attempted = False  # let a later build try again
        return
    prices = {p.id: p.price_label for p in products if p.id and p.amount}
    if prices:
        state.license_prices = prices
```

**WHY**: Prices change; Worker is source of truth. `_prices_attempted` reset on failure allows retry on next render.

**CollabShell gap** (`src/screens/settings/premium_section.py:52-58, 315-340`, **Audit-03 #11**):
```python
_PRICES_ATTEMPTED = False  # Module-level global

async def _load_prices(ev=None):
    global _PRICES_ATTEMPTED
    if _PRICES_ATTEMPTED and prices:
        return
    _PRICES_ATTEMPTED = True
    # ... fetch ...
    except Exception as ex:
        logger.warning("Premium catalog failed: %s", ex)
        state.license_prices = {}
        # _PRICES_ATTEMPTED stays True! Never retries automatically.
```

On fetch failure, `_PRICES_ATTEMPTED` stays `True` and `prices` becomes `{}`. Next render sees `_PRICES_ATTEMPTED and prices` → `True and False` → `False`, so it doesn't return early, but `_PRICES_ATTEMPTED` is still `True` so it never retries.

**Adopt this first**: Set `_PRICES_ATTEMPTED = False` in the except block (exactly like DDGS line 176).

---

### 2.3 Restore Purchases — Token-Issuing Path (`/restore`), Not `/status`

**DDGS** (`src/services/premium_service.py:250-282`):
```python
async def reconcile(self) -> None:
    # Uses the TOKEN-ISSUING path on purpose: /status never re-issues
    # the signed token, so after a renewal the cached token's exp would
    # lapse while the server still said active - a paying subscriber
    # locked out until a manual Restore. restore() answers the same and
    # re-arms the token in one round-trip (same rate bucket).
    recovery_id = await self.license.recovery_id()
    if not recovery_id:
        self._recompute_premium()
        return
    try:
        await self.license.restore(recovery_id)
    ...
```

**WHY**: `/restore` issues a new signed token; `/status` does not. A renewal extends `exp` on the server but the client's cached token would expire — only `/restore` re-arms it.

**CollabShell** (`src/services/premium_service.py:105-134`): Same logic — **correctly ported**.

---

### 2.4 Play Store Links — Only Where Allowed, Never in Play Build

**DDGS** (`src/components/update_dialog.py:147-190`, `src/components/settings/sections_about.py:39-71`):
```python
# update_dialog.py - Play channel offers Google Play ONLY:
elif CHANNEL == "play":
    if playstore_url:
        actions.append(ft.FilledButton(
            "Google Play",
            icon=ft.Icons.SHOP_ROUNDED,
            action=ft.OpenUrl(playstore_url),
        ))

# sections_about.py - "More apps" and "Rate" split by platform:
def _more_apps_url(page) -> str:
    return KIRI_APPS_PLAY_URL if _is_store_device(page) else KIRI_APPS_URL

def _rate_url(page) -> str:
    return PLAY_STORE_URL if _is_store_device(page) else GITHUB_REPO_URL
```

**WHY**: Play safe-link policy — a store build never points at another store (GitHub). Direct build offers GitHub only (Play edition is different feature set).

**CollabShell**: Has similar logic in `update_dialog.py` and `sections_about.py` — need to verify against DDGS.

---

### 2.5 Recovery ID — Stored Immediately After Checkout, Before Browser Opens

**DDGS** (`src/components/settings/sections_premium.py:337-353`):
```python
# Record the recovery ID BEFORE opening the browser. A browser that
# will not open is the most common checkout failure, and it must not
# be the case that loses the only artifact that restores the purchase.
state.license_recovery_id = order.recovery_id
if order.checkout_url:
    try:
        await launch_url(order.checkout_url, page)
    except Exception as exc:
        _snack(f"Could not open the payment page ({exc}). Your recovery ID is {order.recovery_id}...", "error")
        return
```

**CollabShell** (`src/screens/settings/premium_section.py:463-484`): Same pattern — **correctly ported**.

---

## 3. Wallet / Credits Patterns

### 3.1 Credit Display — Color-Coded Pill in Header

**DDGS** (`src/components/wallet.py:25-61`):
```python
def _credit_color(credits: int) -> str:
    if credits > 20:
        return AppColors.SUCCESS
    if credits >= 5:
        return AppColors.WARNING
    return AppColors.ERROR

def build_credit_pill(page: ft.Page, credits: int) -> ft.Container:
    color = _credit_color(credits)
    return ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED, size=tokens.ICON_SM, color=color),
            ft.Text(str(credits), size=tokens.FONT_SM, weight=ft.FontWeight.W_600, color=color),
        ], spacing=4, tight=True),
        padding=ft.Padding(8, 4, 10, 4),
        border_radius=tokens.RADIUS_PILL,
        bgcolor=ft.Colors.with_opacity(0.12, color),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.25, color)),
        ink=True,
        tooltip="Assistant credits, tap for details",
        on_click=lambda e: show_wallet_dialog(page),
    )
```

**CollabShell** (`src/components/credit_pill.py`): Similar reactive component — **correctly ported** per Audit-03 #18.

---

### 3.2 Wallet Dialog — Balance, Cost Table, Ad Top-Up (Mobile Only)

**DDGS** (`src/components/wallet.py:64-328`):
- Shows balance with color coding
- Cost table generated from `COST_STEP` via `credit_word()` — never typed by hand
- Ad top-up row **only renders where ads can play** (native mobile, non-premium):
```python
ads_available = bool(ad_service) and ad_service._is_mobile()
# ...
if ads_available and not is_premium:
    rows.extend([... watch-ad row ...])
if ads_available and not is_premium:
    actions = [cooldown_label, watch_btn]
elif not is_premium and CHANNEL != "play":
    actions = [ft.TextButton("Get 500 credits a day", on_click=_open_premium)]
else:
    actions = []
```

**WHY**: Desktop/web have no ads to watch — offering "watch ad" there is a dead affordance. Desktop users are pointed at Premium instead.

**CollabShell gap** (`src/components/wallet_dialog.py:176-234`):
```python
def _ads_available() -> bool:
    if ad_service is None or is_premium:
        return False
    probe = getattr(ad_service, "_is_mobile", None)
    return bool(probe() if callable(probe) else probe)

can_ads = _ads_available()
# ...
actions=[... watch_btn if can_ads else premium_button ...]
```
**Audit-03 #8**: The comment says "a truthy bound method here made desktop offer an ad top-up" — but the code **calls** the method (`probe()`), so it correctly gets the boolean result. This appears to be **fixed** (the comment describes the old bug).

---

### 3.3 Ad Top-Up Cooldown — 30 Seconds, Respects Premium

**DDGS** (`src/components/wallet.py:131-208`, constants `AD_TOPUP_COOLDOWN_SEC = 30.0`, `AD_TOPUP_CREDITS = 2`):
```python
async def _on_watch(e):
    if state.is_premium:
        return
    now = time.time()
    if state.ad_cooldown_end > now:
        cooldown_label.value = f"Wait {int(state.ad_cooldown_end - now)}s."
        return
    state.ad_cooldown_end = now + AD_TOPUP_COOLDOWN_SEC
    # ... show rewarded interstitial ...
    ok = await ad_service.show_rewarded_interstitial(_on_watch_success)
    if not ok:
        # Nothing was shown, so nothing was earned and nothing should
        # be locked out: hand the button straight back.
        state.ad_cooldown_end = 0.0
        watch_btn.disabled = False
```

**WHY**: Cooldown only applied when ad actually shows. If `show_rewarded_interstitial` returns `False` (no ad available), cooldown is **cleared** so user can retry immediately.

**CollabShell** (`src/components/wallet_dialog.py:134-174`): Same logic — **correctly ported**.

---

### 3.4 Credit Economy — 3-Phase Settlement (Reserve/Commit/Rollback)

**DDGS** (`src/services/credit_service.py:64-171`):
```python
async def reserve(self, amount: int) -> str | None:
    # Check and reserve as ONE STEP under lock (TOCTOU fix)
    async with self._lock:
        current = await self._get_credits()
        total_reserved = sum(self._reservations.values())
        if current - total_reserved < amount:
            return None
        self._reservations[tx_id] = amount
        self._active.add(tx_id)
    self._arm_rollback(tx_id, amount)
    return tx_id

async def commit_amount(self, tx_id: str, amount: int | None = None) -> int:
    # Read held amount UNDER LOCK (old commit read outside lock)
    async with self._lock:
        self._active.discard(tx_id)
        if tx_id not in self._reservations:
            return await self._get_credits()  # idempotent
        held = self._reservations.pop(tx_id, 0)
        if amount is None:
            amount = held
        # ... deduct ...
```

**Key DDGS patterns**:
- Reserve checks available = `balance - sum(reservations)` under lock (prevents double-spend)
- Commit reads held amount **under lock** (old bug: read outside lock → rollback between read and settle billed zero)
- Idempotent commit: second call with same tx_id finds no hold and returns without charging
- `reserve_more` extends hold without resetting rollback clock
- Auto-rollback after 240s, but **defers if turn still active** (up to 3 deferrals)

**CollabShell** (`src/services/credit_service.py:97-168`, **Audit-03 #16**): Math matches DDGS exactly — **correctly ported**.

---

### 3.5 Daily Reset — UTC Midnight, Flat Reset (No Rollover)

**DDGS** (`src/services/credit_service.py:250-284`):
```python
async def _check_daily_reset(self) -> None:
    today = datetime.now(tz=UTC).date().isoformat()
    if self._reset_day == today:
        return
    last_reset = await self._storage.get(STORAGE_LAST_RESET)
    if last_reset == today:
        self._reset_day = today
        return
    async with self._lock:
        if self._reset_day == today:
            return
        daily_cap = await self.get_daily_cap()
        new_balance = daily_cap  # FLAT RESET: no ad-credit rollover
        await self._storage.set(STORAGE_CREDITS, str(new_balance))
        await self._storage.set(STORAGE_LAST_RESET, today)
        state.credits_remaining = new_balance
        self._reset_day = today
        # Deliberately NOT clearing self._reservations. A turn in flight
        # at midnight holds a reservation it is about to settle; clearing
        # it made that turn's later commit find nothing and silently
        # charge zero for delivered work.
```

**WHY**: Runs on every balance read (not just at launch) so an app left open across midnight refills. Reservations preserved across reset to avoid free turns.

**CollabShell** (`src/services/credit_service.py:73-85`): Same flat reset — **correctly ported**.

---

### 3.6 Checkout Watcher — Polls `/restore`, Aborts on 402/403, Continues on 404

**DDGS** (`src/services/premium_service.py:347-395`):
```python
async def _checkout_watch_loop(self, recovery_id: str) -> None:
    deadline = time.monotonic() + CHECKOUT_WATCH_TIMEOUT
    failures = 0
    while time.monotonic() < deadline:
        backoff = min(30.0, CHECKOUT_WATCH_INTERVAL * failures)
        await asyncio.sleep(CHECKOUT_WATCH_INTERVAL + random.uniform(0, CHECKOUT_WATCH_INTERVAL) + backoff)
        try:
            status = await self.license.restore(recovery_id)  # TOKEN-ISSUING path
            failures = 0
        except LicenseUnavailable as ex:
            if ex.is_refusal and ex.status_code in WATCHER_ABORT_CODES:  # 402, 403
                logger.info("Checkout watcher aborted: %s", ex)
                return  # Hard refusal - stop polling
            failures += 1
            logger.info("Checkout watcher waiting: %s", ex)
            continue  # 404 = webhook lag, keep waiting
        ...
        if status.status in ("active", "grace") and self.license.unlocked:
            self._notify(unlock_message(self.page))
            return
```

**WHY**: 
- Uses `/restore` (token-issuing) not `/status` — re-arms token on renewal
- `WATCHER_ABORT_CODES = {402, 403}` — payment invalid / app not entitled (never self-heals)
- **404 NOT abortive** — webhook lag, record may not exist yet
- Backoff + jitter prevents hammering

**CollabShell** (`src/services/premium_service.py:189-239`, **Audit-03 #15**): Behavior matches DDGS — **correctly ported** (tests pass).

---

## 4. Settings Sections Patterns

### 4.1 Settings Architecture — Section Builders Return Containers

**DDGS** (`src/components/settings/__init__.py`, `src/screens/settings_screen.py`):
- Each section is a function `build_xxx_section(page, ...)` returning `ft.Container` (via `AppStyles.section_card`)
- Sections composed in `SettingsScreen` by calling builders
- Observable state drives repaints — no control mutation

**CollabShell** (`src/screens/settings/__init__.py`): Same pattern — **correctly ported**.

---

### 4.2 Section: AI (Assistant & Premium) — `sections_ai.py`

**DDGS** (`src/components/settings/sections_ai.py`):
- Assistant mode switch (AI on/off)
- Thinking depth: SegmentedButton (Auto/Fast/Deep)
- Assistant model: row with live status subtitle + "Change" button
- Credits remaining: "X of Y credits left today"
- Cost table: generated from `COST_STEP` via `credit_word()` — "Each Assistant model step costs 1 credit. Search, scraping, downloads, overviews and summaries are free"
- Scheduled crawls: editable interval via SegmentedButton dialog

**Key pattern**: `credit_word(COST_STEP)` ensures copy never drifts from actual cost.

**CollabShell**: Has similar AI settings — verify cost table uses `credit_word`.

---

### 4.3 Section: Premium — `sections_premium.py` (covered in §2)

---

### 4.4 Section: General — `sections_general.py`

**DDGS** (`src/components/settings/sections_general.py`):
- Display Theme: three cards (Light/Dark/System) with selection border
- Search Rules: SafeSearch chips, Region dropdown, Max Results slider, Time Limit dropdown
- All controls bound to `state.xxx` with `page.run_task(set_fn, key, value)`

---

### 4.5 Section: Advanced — `sections_advanced.py`

**DDGS** (`src/components/settings/sections_advanced.py`):
- Search Sources: backend dropdown
- Content Extraction: format dropdown
- Downloads: video quality dropdown + Play channel notice
- Connection & Proxy: proxy text field + SSL verify switch
- Performance: max worker threads slider

**Play channel notice** (line 108-113):
```python
+ (
    " (YouTube downloads are disabled in this Play Store "
    "edition. See About.)"
    if CHANNEL == "play"
    else ""
),
```

---

### 4.6 Section: About — `sections_about.py`

**DDGS** (`src/components/settings/sections_about.py`):
- Play edition banner (only on Play channel)
- "Built with ddgs (MIT) + primp"
- Contact / Rate / More Apps rows — platform-honest URLs:
```python
def _more_apps_url(page) -> str:
    return KIRI_APPS_PLAY_URL if _is_store_device(page) else KIRI_APPS_URL

def _rate_url(page) -> str:
    return PLAY_STORE_URL if _is_store_device(page) else GITHUB_REPO_URL
```
- Version header: tappable, opens update dialog, shows "Update available" when `state.update_available`
- Privacy / Terms buttons

---

### 4.7 Version Resolution — `version.py`

**DDGS** (`src/components/settings/version.py:3-28`):
```python
# Priority: installed package metadata → pyproject.toml → hard fallback
try:
    from importlib.metadata import version as _pkg_version
    _APP_VERSION = _pkg_version("ddgs-app")
except Exception:
    _APP_VERSION = ""
if not _APP_VERSION:
    try:
        import tomllib
        _pp = Path(__file__).resolve().parent.parent.parent.parent / "pyproject.toml"
        _APP_VERSION = tomllib.load(_pp)["project"]["version"]
    except Exception:
        _APP_VERSION = ""
if not _APP_VERSION:
    _APP_VERSION = "2.1.0"
```

**WHY**: Each stage independently guarded — failure at one cannot mask the next. Always a non-empty string.

---

## 5. App Shell / Header / Update Dialog / AI Cards

### 5.1 AppShell — Onboarding vs Dashboard Branching

**DDGS** (`src/app_shell.py:30-111`):
```python
@ft.component
def AppShell() -> Control:
    if not state.has_accepted_terms:
        from screens.onboarding_screen import OnboardingScreen
        screen = OnboardingScreen()
    elif state.search_active:
        from screens.results_screen import ResultsScreen
        screen = ResultsScreen()
    else:
        if state.selected_tab == 1:
            from screens.history_screen import HistoryScreen
            screen = HistoryScreen(key=ft.ValueKey("history"))
        elif state.selected_tab == 2:
            from screens.settings_screen import SettingsScreen
            screen = SettingsScreen(key=ft.ValueKey("settings"))
        else:
            from screens.home_screen import HomeScreen
            screen = HomeScreen(key=ft.ValueKey("home"))
```

**WHY**: Clean branching on observable state. `ft.ValueKey` forces remount on tab switch (preserves scroll position per tab).

**NavigationBar sync** (lines 37-83): Imperative attachment to `page.views[0].navigation_bar` via `use_effect` — deliberate escape hatch (KTV Player pattern).

**FAB sync** (lines 112-183): Shows "Ask Assistant" or "Back to Assistant" based on `chat_minimized` / `chat_open` / `credits_remaining`.

---

### 5.2 AppHeader — Live Version Chip

**DDGS** (`src/components/app_header.py:27-106`):
```python
def _build_version_chip(page: ft.Page | None) -> ft.Control:
    update_available = getattr(state, "update_available", False)
    if update_available:
        # Morphs into accented "Update: {version} Available!" with primary border + dot
        return ft.Container(
            content=ft.Row([ft.Text(f"Update: {label} Available!", color=AppColors.PRIMARY), ft.Container(width=6, height=6, border_radius=3, bgcolor=AppColors.PRIMARY)]),
            border=ft.Border.all(1.5, AppColors.PRIMARY),
            bgcolor=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
            on_click=_open_dialog,
        )
    # Normal: "v{_APP_VERSION}" subtle pill
    return ft.Container(content=ft.Text(f"v{_APP_VERSION}", color=ft.Colors.ON_SURFACE_VARIANT), ...)
```

**WHY**: Version chip is the update entry point — always clickable. Morphs visually when update available.

**CollabShell**: Has similar `version_dialog.py` and header — verify chip morphs.

---

### 5.3 Update Dialog — Two Modes, Channel-Honest Destinations

**DDGS** (`src/components/update_dialog.py:14-264`):
```python
# Mode 1: Update available
if CHANNEL == "play":
    # Play safe-link: Google Play ONLY
    actions.append(ft.FilledButton("Google Play", action=ft.OpenUrl(playstore_url)))
else:
    # Direct build: GitHub ONLY (keeps this build's feature set)
    actions.append(ft.FilledButton("Direct APK (GitHub)" if is_android else "Download from GitHub", action=ft.OpenUrl(github_url)))

# Mode 2: Up to date
# Shows installed version + bundled changelog + live re-check button
# NEVER fabricates an update the feed didn't announce
```

**WHY**: A store build never points at another store. Direct build offers GitHub only (Play edition is different feature set).

---

### 5.4 AI Overview Card — Passive, Free, Collapsed by Default

**DDGS** (`src/components/ai_overview.py:49-280`):
- Only renders when `state.ai_mode_enabled` and `state.ai_overview` exists
- Collapsed: clamped markdown (150px) + "Read full report" button
- Expanded: full markdown + source rows with thumbnails + related pills
- "Ask Assistant" button pre-fills deeper question
- Error states: credits exhausted, midstream loss, unavailable — honest copy

---

### 5.5 AI Summary Card — Passive Page Summary

**DDGS** (`src/components/ai_summary.py:25-253`):
- Built by host (Reader, preview sheet, detail sheet) — `build_auto_summary()` returns `(card, start)`
- `start(force=True)` on navigation; no-op while stream runs
- Streams tokens via `on_token` callback, throttles UI updates to 0.2s
- Terminal actions only: "Ask Assistant about this page" or "Get credits" — no button to begin

---

### 5.6 Model Picker — Live State, Shared Between Pill and Settings

**DDGS** (`src/components/model_picker.py:32-122`):
```python
@dataclass(frozen=True)
class PickerState:
    label: str
    discovering: bool
    selected: str
    active: bool  # True only when saved choice is in catalog we hold
    models: tuple[dict, ...]
    message: str = ""
    action: str = ""

def model_picker_state() -> PickerState:
    # Derives label from state.ai_router_status and catalog
    # "Starting router...", "Loading models...", "Offline", or model name
    # active=True only when current selection exists in live catalog
```

**WHY**: Label logic shared by chat header pill and Settings row — they can never disagree. A saved preference can never outlive the router itself.

---

## 6. License / Crypto Patterns

### 6.1 License Token Format — `v1.<b64url payload>.<b64url signature>`

**DDGS** (`src/services/license_token.py:3-9, 154-226`):
- Worker signs with ECDSA P-256 / SHA-256 via WebCrypto
- Signature is **raw r‖s** (IEEE P1363, 64-byte) over ASCII bytes of payload segment
- Verification is pure Python (no crypto dependency) — no wheel for Android, no cross-compile

---

### 6.2 Token Verification — Strict Claims Checks

**DDGS** (`src/services/license_token.py:154-226`):
```python
def verify_token(token: str, public_key: str, app_id: str, *, now: float | None = None) -> LicenseClaims:
    # 1. Format: v1.payload.signature
    # 2. Signature: raw r||s over payload_b64 ASCII bytes (not decoded JSON)
    # 3. Claims validation:
    #    - iss == "license.kiri.ng"
    #    - app == app_id
    #    - v == 1
    #    - status in ("active", "grace")
    #    - exp > now (if present) — expired raises TokenRejected("expired")
    #    - iat, exp must be integers (type(claims_raw.get("iat")) is int)
```

**WHY**: Every numeric claim validated — a signed token carrying string/non-finite `exp` is rejected as malformed, not raising ValueError into settings handler.

---

### 6.3 Token Rejection Reasons — Machine-Readable

**DDGS** (`src/services/license_token.py:41-47`):
```python
class TokenRejected(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}{': ' + detail if detail else ''}")
        self.reason = reason
        self.detail = detail
```

Reasons: `missing_token`, `malformed_token`, `bad_signature`, `bad_issuer`, `wrong_app`, `unsupported_version`, `expired`, `revoked`, `unknown_status`, `bad_public_key`, `malformed_claims`.

**WHY**: UI can say what went wrong instead of generic failure.

---

### 6.4 License Service — Worker Authoritative, Token Is Offline Cache

**DDGS** (`src/services/license_service.py:1-22`):
> The Worker is authoritative; the token it returns is a signed cache that keeps premium working offline. Nothing here unlocks premium by itself — a verified token or a live server response must say so first.

**Key rules**:
- `apply_cached_token()` verifies stored token offline — premium survives no network
- Rejected token is **cleared** (not left to fail every boot)
- `reconcile()` uses `/restore` (token-issuing) not `/status` — re-arms token on renewal
- `status_refusal(code)` = 402, 403, 404 — **400 deliberately excluded** (malformed request = app bug, never revokes real license)

**CollabShell gap — CRITICAL** (`src/services/license_service.py:73-81`, **Audit-03 #2**):
```python
# CollabShell INCLUDES 400:
def status_refusal(code: int) -> bool:
    return code in (402, 403, 404)  # 400 INCLUDED in CollabShell, NOT in DDGS
```
DDGS explicitly excludes 400: *"a malformed request is an app bug and must never revoke a real license"*. Including 400 means a transient serialization bug permanently revokes Premium until manual restore.

---

### 6.5 License Token — Enhanced Verification in CollabShell (Compatibility Risk)

**CollabShell** (`src/services/license_token.py:39-51, 190-217, 241-317`, **Audit-03 #6, #14**):
Adds validations NOT in DDGS:
- Strict SPKI validation: exact 91 bytes, correct prefix (vs DDGS suffix-only scan)
- Payload size limits: 8KB payload, 200B signature (DoS prevention)
- Clock skew tolerance: 300s for future `iat`
- `nbf` (not-before) claim support
- `paid_through` type enforcement
- Scope validation (`_check_scope`) — mirrors Worker's `scopeAllows`

**Risk**: Worker compatibility. If Worker changes token structure, verification breaks. DDGS has none of these.

**Decision needed**: Document as deliberate hardening + ensure Worker matches, OR align with DDGS.

---

### 6.6 Premium Service — Single Source of Truth for `is_premium`

**DDGS** (`src/services/premium_service.py:102-110, 167-176, 183-214`):
```python
def apply_entitlement() -> bool:
    resolved = bool(getattr(state, "play_premium_active", False)) or bool(
        getattr(state, "license_premium_active", False)
    )
    if getattr(state, "is_premium", False) != resolved:
        state.is_premium = resolved
    return resolved

def _recompute_premium(self) -> None:
    # Play channel contributes independently, so both are ORed
    state.license_premium_active = bool(self.license.unlocked)
    # ... derive status from claims ...
    self._commit()  # logs transition, notifies listeners

def _commit(self) -> None:
    previous = bool(state.is_premium)
    resolved = apply_entitlement()
    if resolved != previous:
        logger.info("Premium state -> %s", resolved)  # Diagnosable in field
    self._notify_listeners()
```

**WHY**: 
- `apply_entitlement()` is the **single place** derived flag is written
- `_commit()` logs every transition — makes wrong premium state diagnosable
- Listeners notify Settings screen to repaint (card is built from observable state)
- Play channel and Kiri License are independent — ORed together

**CollabShell** (`src/services/premium_service.py:59-64`): Same pattern — **correctly ported**.

---

### 6.7 Checkout Watcher — Lives on Service, Not Screen

**DDGS** (`src/services/premium_service.py:322-339`):
```python
def start_checkout_watch(self, recovery_id: str) -> None:
    # Lives on the service (not the Settings screen) so navigating away
    # or rebuilding the tab cannot orphan it (KTV Player).
```

**CollabShell** (`src/services/premium_service.py:172-181`): Same — **correctly ported**.

---

### 6.8 Platform-Honest Unlock Message

**DDGS** (`src/services/premium_service.py:63-80`):
```python
def page_has_ads(page) -> bool:
    try:
        return bool(page.platform.is_mobile()) and not getattr(page, "web", False)
    except Exception:
        return True  # Unknown page -> assume ads (most installs are phone APKs)

def unlock_message(page) -> str:
    if page_has_ads(page):
        return "Premium unlocked. Ads removed."
    return f"Premium unlocked. {PREMIUM_DAILY_CREDITS} credits a day."
```

**WHY**: Desktop/web have no ads — saying "ads removed" there would be a lie. Unknown platform assumes ads (most installs are phone APKs).

**CollabShell gap — HIGH** (`src/services/premium_service.py:241-255`, **Audit-03 #4**):
```python
def _notify_premium_unlocked(self) -> None:
    # ...
    try:
        if self.page.platform.is_mobile():  # RAISES on desktop/web!
            snack("Premium unlocked. Ads removed.")
        else:
            snack("Premium unlocked.")
    except Exception:
        logger.debug("Could not show the unlock notice", exc_info=True)
```
`page.platform.is_mobile()` raises `FletUnsupportedPlatformException` on desktop/web (per `flet_ads.base_ad.BaseAd.before_update`).

**Adopt this first**: Use `page_has_ads(page)` helper (already defined in `premium_section.py:76-91`) or wrap in try/except.

---

## CollabShell Gaps — Prioritized "Adopt This First" List

| Priority | Pattern Area | DDGS Reference | CollabShell Gap | Audit-03 Ref |
|----------|--------------|----------------|-----------------|--------------|
| **1** | Rewarded ad grants credits without showing ad | `ad_service.py:305-312` (returns `False`, no `on_close`) | Calls `on_close` for premium/desktop/no-ads → grants free credits | **#1 Critical** |
| **2** | `status_refusal` excludes HTTP 400 | `license_service.py:73-82` | Includes 400 → client bug revokes valid license | **#2 Critical** |
| **3** | Premium card `_STATUS_COPY` has `"active"` entry | `sections_premium.py:51-56` | Missing `"active"` → free pitch shown to subscribers on first load | **#3 High** |
| **4** | `_notify_premium_unlocked` uses `page_has_ads` helper | `premium_service.py:63-80` | Calls `page.platform.is_mobile()` → crashes on desktop | **#4 High** |
| **5** | Banner ad dimensions hardcoded (320x50) | `ad_service.py:124-128` | Imports `core.tokens` at runtime inside try → fragile | **#5 High** |
| **6** | `_PRICES_ATTEMPTED` reset on catalog fetch failure | `sections_premium.py:176` | Stays `True` on failure → never retries automatically | **#11 Low** |
| **7** | License token verification — align with DDGS or document hardening | `license_token.py` (no scope/size/clock/nbf checks) | Extra validations (scope, size, skew, nbf, paid_through type) — compat risk | **#6 Medium** / **#14 Info** |
| **8** | `reconcile` stamps `_last_reconcile_at` on all early returns | `premium_service.py:267` | Play channel early return doesn't stamp → debounce loops forever | **#7 Medium** |
| **9** | `is_fresh` handles corrupt `fetched_at` gracefully | N/A (DDGS no cache layer) | Parse error → `False` → refetch storm | **#13 Low** |
| **10** | Rewarded interstitial never calls `on_close` on error | `ad_service.py:326-333` | Calls `on_close` in except block → grants credits on error | Related to #1 |

---

## Files Referenced

**DDGS Source** (gold standard):
- `/home/maikel/Desktop/kiri-apps/DDGS/src/services/ad_service.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/services/premium_service.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/services/credit_service.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/services/license_service.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/services/license_token.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/components/wallet.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/components/settings/sections_premium.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/components/settings/sections_ai.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/components/settings/sections_general.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/components/settings/sections_advanced.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/components/settings/sections_about.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/components/settings/version.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/app_shell.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/components/app_header.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/components/update_dialog.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/components/ai_overview.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/components/ai_summary.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/components/model_picker.py`
- `/home/maikel/Desktop/kiri-apps/DDGS/src/core/constants.py`

**CollabShell Source** (audited):
- `/home/maikel/Desktop/kiri-apps/CollabShell/src/services/ad_service.py`
- `/home/maikel/Desktop/kiri-apps/CollabShell/src/services/premium_service.py`
- `/home/maikel/Desktop/kiri-apps/CollabShell/src/services/credit_service.py`
- `/home/maikel/Desktop/kiri-apps/CollabShell/src/services/license_service.py`
- `/home/maikel/Desktop/kiri-apps/CollabShell/src/services/license_token.py`
- `/home/maikel/Desktop/kiri-apps/CollabShell/src/components/wallet_dialog.py`
- `/home/maikel/Desktop/kiri-apps/CollabShell/src/components/credit_pill.py`
- `/home/maikel/Desktop/kiri-apps/CollabShell/src/screens/settings/premium_section.py`
- `/home/maikel/Desktop/kiri-apps/CollabShell/docs/audit-03-ads-premium-license.md`

---

*Generated by ZCode Explore — read-only extraction from DDGS reference implementation*
