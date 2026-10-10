"""Kiri License service — external checkout for everything Play cannot bill.

Verbatim port of ktv-player/src/services/kiri_license.py, with two adapter
shims and nothing else changed:

  * **storage** — ktv-player reads a global ``db_manager``; we take an injected
    storage object exposing ``async get(key, default)`` / ``async set(key, value)``
    (CollabShell's StorageService). The ``token = ""`` clear semantics are kept
    rather than ``delete_key``, matching both KTV and this app's retired-key
    policy of never deleting on-device keys.
  * **http** — a ``_http_client()`` factory so tests can substitute a mock
    transport without patching ``httpx`` globally (the openai SDK subclasses
    it and a global patch breaks at import time).

Everything else — paths, bodies, refusal codes, the retry rule, the ``_query``
persistence decision table, ``_revoke``, ``effective_unlocks`` — is as shipped.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from core.constants import (
    KIRI_LICENSE_APP_ID,
    KIRI_LICENSE_BASE_URL,
    KIRI_LICENSE_PUBLIC_KEY,
    KIRI_LICENSE_TIMEOUT,
    SETTING_PRODUCT,
    SETTING_RECOVERY_ID,
    SETTING_TOKEN,
)
from services.license_token import LicenseClaims, TokenRejected, verify_token

logger = logging.getLogger(__name__)

# Pool stays tight on purpose: connect is cheap, read is the Worker's own
# budget. A widen-the-whole-pool scalar timeout made a dead connect hang as
# long as a slow read.
_LICENSE_TIMEOUT = httpx.Timeout(
    connect=5.0, read=KIRI_LICENSE_TIMEOUT, write=10.0, pool=3.0
)

# 402/403 abort the checkout watcher fast: a payment problem will not fix
# itself, and polling it for 15 minutes wastes the user's battery. 404 is
# deliberately NOT here — a webhook lag looks like a 404 and the payment is
# usually real.
WATCHER_ABORT_CODES = frozenset({402, 403})


def _http_client(timeout: httpx.Timeout = _LICENSE_TIMEOUT) -> httpx.AsyncClient:
    """The httpx client used for license calls (named seam for tests)."""
    return httpx.AsyncClient(timeout=timeout)


class LicenseUnavailable(Exception):
    """The license service could not be reached or refused the request."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        is_refusal: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.is_refusal = is_refusal


def status_refusal(code: int) -> bool:
    """HTTP codes meaning "this entitlement is not valid" — not transport.

    402 payment not valid, 403 app not entitled, 404 license not found.
    400 is deliberately excluded: a malformed request is an app bug and must
    never revoke a real license. 429 is excluded for the same reason — being
    throttled is not losing your purchase.
    """
    return code in (402, 403, 404)


@dataclass(frozen=True)
class LicenseProduct:
    id: str
    amount: float
    currency: str
    kind: str
    description: str

    @property
    def price_label(self) -> str:
        symbol = {"USD": "$", "EUR": "€", "NGN": "₦"}.get(self.currency.upper(), "")
        amount = f"{self.amount:,.2f}".rstrip("0").rstrip(".")
        return f"{symbol}{amount} {self.currency.upper()}".strip()


@dataclass(frozen=True)
class Checkout:
    recovery_id: str
    checkout_url: str
    product: str
    amount: float
    currency: str


@dataclass(frozen=True)
class LicenseStatus:
    status: str
    product: str
    recovery_id: str
    token: str | None = None
    claims: LicenseClaims | None = None

    @property
    def unlocks(self) -> bool:
        """Display only. NEVER gate on this alone."""
        return self.status in ("active", "grace")

    def effective_unlocks(self, claims: LicenseClaims | None) -> bool:
        """The ONLY predicate allowed to grant or drop an unlock."""
        return self.status in ("active", "grace") and claims is not None


class KiriLicenseService:
    """Talks to the Kiri License Worker. Never grants entitlement itself."""

    def __init__(
        self,
        storage,
        app_id: str = KIRI_LICENSE_APP_ID,
        public_key: str = KIRI_LICENSE_PUBLIC_KEY,
        on_change: Callable[[], None] | None = None,
    ):
        self.storage = storage
        self.app_id = app_id
        # Injected so a key rotation (or the test fixtures) needs no monkeypatch.
        self.public_key = public_key
        self.on_change = on_change
        self.products: list[LicenseProduct] = []
        self.claims: LicenseClaims | None = None
        self._unlocked = False

    # ── state ──────────────────────────────────────────────────────────────

    @property
    def unlocked(self) -> bool:
        return self._unlocked

    async def recovery_id(self) -> str:
        return (await self.storage.get(SETTING_RECOVERY_ID, "")) or ""

    async def cached_product(self) -> str:
        return (await self.storage.get(SETTING_PRODUCT, "")) or ""

    async def _store(
        self,
        *,
        recovery_id: str | None = None,
        token: str | None = None,
        product: str | None = None,
    ) -> None:
        """Persist the given keys. Passing "" clears (there is no delete)."""
        if recovery_id is not None:
            await self.storage.set(SETTING_RECOVERY_ID, recovery_id)
        if token is not None:
            await self.storage.set(SETTING_TOKEN, token)
        if product is not None:
            await self.storage.set(SETTING_PRODUCT, product)

    async def _revoke(self, reason: str) -> None:
        """Drop entitlement in memory AND on disk, in one place."""
        self._unlocked = False
        self.claims = None
        await self._store(token="")
        logger.info("Kiri license revoked (%s); cached token cleared", reason)
        self._notify_change()

    async def _apply(self, status: str, claims: LicenseClaims | None) -> None:
        self._unlocked = LicenseStatus(
            status=status, product="", recovery_id=""
        ).effective_unlocks(claims)
        logger.info(
            "Kiri license status=%s product=%s unlocked=%s",
            status,
            claims.product if claims else "-",
            self._unlocked,
        )
        self._notify_change()

    async def apply_cached_token(self) -> bool:
        """Unlock from the stored token with no network. False is not an error:
        it means "nothing cached", "cached but rejected", or "cached but not
        unlocking" — the caller shows the same free state either way.
        """
        token = (await self.storage.get(SETTING_TOKEN, "")) or ""
        if not token:
            self._unlocked = False
            self.claims = None
            self._notify_change()
            return False
        try:
            claims = verify_token(token, self.public_key, self.app_id)
        except TokenRejected as ex:
            logger.info("Cached license token rejected: %s", ex.reason)
            # A rejected token is cleared, not left to fail again every boot.
            await self._revoke(f"cached token rejected: {ex.reason}")
            return False
        self.claims = claims
        await self._apply(claims.status, claims)
        return self._unlocked

    # ── catalog / checkout ────────────────────────────────────────────────

    async def fetch_catalog(self, force: bool = False) -> list[LicenseProduct]:
        """Products and live prices. Cached; `force` re-fetches."""
        if self.products and not force:
            return self.products
        try:
            async with _http_client() as client:
                response = await client.get(
                    f"{KIRI_LICENSE_BASE_URL.rstrip('/')}/catalog"
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as ex:
            raise LicenseUnavailable(
                f"Could not reach the license service: {ex}"
            ) from ex
        if not isinstance(payload, dict):
            raise LicenseUnavailable("The license service returned an invalid response")
        products = []
        for item in payload.get("products", []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            try:
                amount = float(item.get("amount") or 0)
            except (TypeError, ValueError) as ex:
                raise LicenseUnavailable(
                    f"Invalid product pricing for {item.get('id')}: {ex}"
                ) from ex
            products.append(
                LicenseProduct(
                    id=str(item["id"]),
                    amount=amount,
                    currency=str(item.get("currency") or "USD"),
                    kind=str(item.get("kind") or "one_time"),
                    description=str(item.get("description") or ""),
                )
            )
        self.products = products
        return self.products

    async def checkout(self, product_id: str, email: str) -> Checkout:
        """Start a hosted payment and return where to send the user.

        Email only, exactly like KTV Player: the hosted Flutterwave page
        collects everything else, so this app never sees card details.
        """
        product_id = (product_id or "").strip()
        email = (email or "").strip().lower()
        if not product_id:
            raise LicenseUnavailable("Choose a product first")
        if not email or "@" not in email:
            raise LicenseUnavailable("Enter a valid email for your receipt")

        try:
            async with _http_client() as client:
                response = await client.post(
                    f"{KIRI_LICENSE_BASE_URL.rstrip('/')}/checkout",
                    json={
                        "app_id": self.app_id,
                        "product_id": product_id,
                        "email": email,
                    },
                )
        except Exception as ex:
            raise LicenseUnavailable(
                f"Could not reach the license service: {ex}"
            ) from ex
        if response.status_code >= 400:
            raise LicenseUnavailable(
                self._error_message(response, "Checkout failed"),
                status_code=response.status_code,
                is_refusal=status_refusal(response.status_code),
            )
        try:
            payload = response.json()
        except Exception as ex:
            raise LicenseUnavailable(
                "The license service returned invalid JSON"
            ) from ex
        if not isinstance(payload, dict):
            raise LicenseUnavailable("The license service returned an invalid response")
        try:
            amount = float(payload.get("amount") or 0)
            currency = str(payload.get("currency") or "USD")
        except (TypeError, ValueError) as ex:
            raise LicenseUnavailable(f"Invalid order pricing: {ex}") from ex

        checkout = Checkout(
            recovery_id=str(payload.get("recovery_id") or ""),
            checkout_url=str(payload.get("checkout_url") or ""),
            product=str(payload.get("product") or product_id),
            amount=amount,
            currency=currency,
        )
        if not checkout.checkout_url or not checkout.recovery_id:
            raise LicenseUnavailable("The license service returned an incomplete order")
        # Persist the recovery ID immediately: it is the only way back in
        # after the user clears app data.
        await self._store(recovery_id=checkout.recovery_id, product=checkout.product)
        return checkout

    async def restore(self, recovery_id: str) -> LicenseStatus:
        """Redeem a recovery ID (new device / reinstall). Issues a token."""
        return await self._query("/restore", recovery_id, issue_token=True)

    async def refresh(self) -> LicenseStatus | None:
        """Re-check the stored entitlement. None when no ID is stored.

        ``/status`` never issues a token, so it cannot re-arm a renewal — that
        is why reconcile uses ``/restore`` instead.
        """
        recovery_id = await self.recovery_id()
        if not recovery_id:
            return None
        return await self._query("/status", recovery_id, issue_token=False)

    def _notify_change(self) -> None:
        if self.on_change is not None:
            self.on_change()

    # ──────────── transport ────────────────────────────

    async def _post(self, path: str, body: dict) -> dict:
        """One POST. Callers decide retry; this never retries on its own."""
        try:
            async with _http_client() as client:
                response = await client.post(
                    f"{KIRI_LICENSE_BASE_URL.rstrip('/')}{path}", json=body
                )
        except Exception as ex:
            raise LicenseUnavailable(
                f"Could not reach the license service: {ex}"
            ) from ex
        if response.status_code >= 400:
            raise LicenseUnavailable(
                self._error_message(response, "Restore failed"),
                status_code=response.status_code,
                is_refusal=status_refusal(response.status_code),
            )
        try:
            payload = response.json()
        except Exception as ex:
            raise LicenseUnavailable(
                "The license service returned invalid JSON"
            ) from ex
        if not isinstance(payload, dict):
            raise LicenseUnavailable("The license service returned an invalid response")
        return payload

    async def _query(
        self, path: str, recovery_id: str, *, issue_token: bool
    ) -> LicenseStatus:
        if not (recovery_id or "").strip():
            raise LicenseUnavailable("Enter the recovery ID from your purchase email")

        # One immediate retry on a TRANSIENT failure, zero backoff: the retry
        # is for a dropped connection, not a busy server. A refusal never
        # retries — it revokes and surfaces, because retrying a 403 will not
        # make the Worker change its mind.
        try:
            payload = await self._post(
                path, {"app_id": self.app_id, "recovery_id": recovery_id}
            )
        except LicenseUnavailable as ex:
            if ex.is_refusal:
                await self._revoke(f"server refusal HTTP {ex.status_code}")
                raise
            logger.info("License request transient failure, retrying once: %s", ex)
            # A second transient failure propagates unchanged: neither store
            # nor revoke, so the next boot retries from the cached token —
            # which is the safe default.
            payload = await self._post(
                path, {"app_id": self.app_id, "recovery_id": recovery_id}
            )

        status = str(payload.get("status") or "unknown")
        token = payload.get("token") if issue_token else None
        if issue_token and token is not None and not isinstance(token, str):
            raise LicenseUnavailable("The license service returned a malformed token")

        claims: LicenseClaims | None = None
        if token:
            try:
                claims = verify_token(token, self.public_key, self.app_id)
            except TokenRejected as ex:
                # An unverifiable token is refused loudly, not cached: a
                # forged or wrong-app token must never sit on disk.
                await self._revoke(f"token rejected: {ex.reason}")
                raise LicenseUnavailable(
                    "The license service returned a token this app could not verify"
                ) from ex

        # Persistence: a verified unlocking token is cached; a verified token
        # for any other status is NOT (never cache a revocation); a status-only
        # refresh stores the recovery id and product, leaving the token alone.
        if claims is not None and status in ("active", "grace"):
            await self._store(
                recovery_id=str(payload.get("recovery_id") or recovery_id),
                token=token,
                product=str(payload.get("product") or ""),
            )
        elif claims is not None:
            logger.info("Not caching token for status=%s", status)
            await self._store(
                recovery_id=str(payload.get("recovery_id") or recovery_id),
                token="",
                product=str(payload.get("product") or ""),
            )
        else:
            await self._store(
                recovery_id=str(payload.get("recovery_id") or recovery_id),
                product=str(payload.get("product") or ""),
            )

        # Read the old claims BEFORE overwriting: a /status refresh returns no
        # token, and assigning None here would wipe the offline cache.
        effective = claims if claims is not None else self.claims
        if claims is not None:
            self.claims = claims

        if status not in ("active", "grace"):
            await self._revoke(f"server status={status}")
            effective = None
        await self._apply(status, effective)

        return LicenseStatus(
            status=status,
            product=str(payload.get("product") or ""),
            recovery_id=str(payload.get("recovery_id") or recovery_id),
            token=token,
            claims=claims,
        )

    @staticmethod
    def _error_message(response, fallback: str) -> str:
        """Prefer the Worker's own wording, so the user sees the real reason."""
        try:
            body = response.json()
            if isinstance(body, dict) and body.get("message"):
                return str(body["message"])
            if isinstance(body, dict) and body.get("error"):
                return str(body["error"])
        except Exception:
            pass
        return f"{fallback} (HTTP {response.status_code})"
