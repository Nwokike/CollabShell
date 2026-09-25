"""Kiri License: the fallback payment channel for users Play cannot serve.

CollabShell is on Google Play, and Play Billing (`premium_service.py`) is the
primary way to become premium. This service is the second door: the Kiri
License Worker at license.kiri.ng, for users Google billing cannot serve —
regions where Play payment is not offered, accounts that cannot use it, and
desktop builds that have no Play Store at all.

The Worker owns payment policy; this module only speaks its documented client
contract (kiri-license/docs/client-integration.md):

    GET  /catalog   product ids, prices, intervals (safe to cache)
    POST /checkout  start a hosted payment, returns recovery_id + url
    POST /restore   authoritative status + a signed token
    POST /status    the same, without a token

Design rules that are not negotiable here:

  - a network failure NEVER removes Premium. Only an authoritative
    `expired`/`revoked` from the server downgrades, and a locally valid
    token keeps access until its own expiry. A paying user must not lose
    Premium because a hotel wifi dropped.
  - the private signing key and the Flutterwave secret never appear here.
    Only the public verification key, which can confirm a signature but
    never produce one.
  - never unlock from a client-side flag alone; a token is proof, a flag
    is not.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from core import constants
from core.license_crypto import TokenError, verify_token

logger = logging.getLogger("license")

BASE_URL = "https://license.kiri.ng"
# Matches [tool.flet] org + product in pyproject. Must never be a temporary
# installation ID: it is half of the identity a license is checked against.
APP_ID = "ng.kiri.collabshell"

TIMEOUT = 15.0
# The catalog is safe to cache per its own docs, and it is the only request
# made on the premium screen's first paint.
CATALOG_TTL = 60 * 60

# Shown when the store channel is the one to use. Kept next to the product
# ids so the two never drift apart.
RECOVERY_RE = re.compile(r"^KIRI-([A-Z])-([A-Z0-9_-]{20,})$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

_catalog_cache: dict[str, Any] = {"at": 0.0, "products": []}

# ── Where this channel is allowed to exist ──────────────────────────────
# KTV Player's model, adopted wholesale: one backend (this Worker), and a
# build-time channel decides whether premium exists at all. The Play AAB
# is stamped CHANNEL = "play" — free-only, no purchase surface, no Worker
# traffic. Every other build (direct APK, desktop, web) sells through
# license.kiri.ng with no Google permission involved.
#
# No runtime opt-in and no platform branch: the artifact carries the
# policy, exactly like KTV's core/channel.py.


def is_available(page=None) -> bool:
    """True when this build offers the direct (Worker) channel.

    `page` is accepted and ignored: the build-time channel marker decides,
    never the platform and never a runtime toggle.
    """
    from core.build_channel import CHANNEL

    return CHANNEL != "play"


class LicenseError(Exception):
    """The Worker refused the request, or could not be reached.

    `code` is the Worker's own error code when it sent one — the
    difference between "the network died" (keep the current verdict) and
    "this recovery ID has no purchase" (definitively drop premium).
    """

    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Product:
    id: str
    code: str
    kind: str
    interval: str | None
    amount: float
    currency: str
    description: str

    @property
    def is_recurring(self) -> bool:
        return self.kind != "one_time"

    @property
    def label(self) -> str:
        return f"{self.currency} {self.amount:.2f}"


@dataclass(frozen=True)
class Entitlement:
    """The outcome of a restore/status call, or of an offline token check."""

    status: str  # active | grace | expired | revoked | unknown
    product: str = ""
    paid_through: int | None = None
    recovery_id: str = ""
    scope: str = ""
    token: str = ""
    offline: bool = False

    @property
    def grants_access(self) -> bool:
        return self.status in ("active", "grace")

    @property
    def is_definitive(self) -> bool:
        """True when the server actually ruled, so a downgrade is safe. A
        network error is not definitive and must never remove access."""
        return self.status in ("active", "grace", "expired", "revoked")


def parse_recovery_id(value: str) -> str | None:
    """Validate a recovery ID's shape without contacting the Worker."""
    text = str(value or "").strip().upper()
    return text if RECOVERY_RE.match(text) else None


def valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(str(value or "").strip()))


def _product_from(raw: dict) -> Product:
    return Product(
        id=str(raw.get("id") or ""),
        code=str(raw.get("code") or ""),
        kind=str(raw.get("kind") or "one_time"),
        interval=raw.get("interval"),
        amount=float(raw.get("amount") or 0.0),
        currency=str(raw.get("currency") or "USD"),
        description=str(raw.get("description") or ""),
    )


async def _get(path: str) -> dict:
    try:
        async with httpx.AsyncClient(http2=False, timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}{path}")
    except Exception as exc:
        raise LicenseError("Could not reach the license server.") from exc
    if response.status_code >= 400:
        raise LicenseError(_error_message(response), _error_code(response))
    return response.json()


async def _post(path: str, payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(http2=False, timeout=TIMEOUT) as client:
            response = await client.post(
                f"{BASE_URL}{path}",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
    except Exception as exc:
        raise LicenseError("Could not reach the license server.") from exc
    if response.status_code >= 400:
        raise LicenseError(_error_message(response), _error_code(response))
    return response.json()


def _error_code(response) -> str:
    try:
        return str((response.json() or {}).get("error", "") or "")
    except Exception:
        return ""


def _error_message(response) -> str:
    """Turn the Worker's error codes into something a person can act on."""
    code = _error_code(response)
    messages = {
        "invalid_recovery_id": "That recovery ID does not look right.",
        "license_not_found": "No purchase was found for that recovery ID.",
        "app_not_entitled": "That purchase is for a different app.",
        "rate_limited": "Too many attempts — wait a minute and try again.",
        "payment_not_valid": "That payment could not be verified.",
        "verification_unavailable": (
            "The payment provider is unreachable. Your access is unchanged — "
            "try again shortly."
        ),
    }
    if code in messages:
        return messages[code]
    return f"The license server returned HTTP {response.status_code}."


async def get_catalog(force: bool = False) -> list[Product]:
    """The purchasable tiers, cached for an hour (the Worker says it is
    safe to cache; the prices are server-side at checkout regardless)."""
    if not force and time.time() - _catalog_cache["at"] < CATALOG_TTL:
        return list(_catalog_cache["products"])
    data = await _get("/catalog")
    products = [_product_from(p) for p in (data.get("products") or [])]
    _catalog_cache["at"] = time.time()
    _catalog_cache["products"] = products
    return products


async def start_checkout(email: str, product_id: str, name: str = "") -> dict:
    """Create a hosted payment. Returns the recovery ID and the URL to open.

    The price is the Worker's, never the client's — that is the whole reason
    the Worker exists instead of the app talking to Flutterwave.
    """
    if not valid_email(email):
        raise LicenseError("Enter a valid email address.")
    return await _post(
        "/checkout",
        {
            "app_id": APP_ID,
            "product_id": product_id,
            "email": email.strip(),
            "name": (name or "").strip()[:120] or None,
        },
    )


def entitlement_from_response(data: dict) -> Entitlement:
    return Entitlement(
        status=str(data.get("status") or "unknown"),
        product=str(data.get("product") or ""),
        paid_through=data.get("paid_through"),
        recovery_id=str(data.get("recovery_id") or ""),
        scope=str(data.get("scope") or ""),
        token=str(data.get("token") or ""),
    )


async def restore(recovery_id: str) -> Entitlement:
    """Restore by recovery ID, after a reinstall or a data wipe."""
    parsed = parse_recovery_id(recovery_id)
    if not parsed:
        raise LicenseError("That recovery ID does not look right.")
    return entitlement_from_response(
        await _post("/restore", {"recovery_id": parsed, "app_id": APP_ID})
    )


async def check_status(recovery_id: str) -> Entitlement:
    """Refresh without minting a new token — for resume and expiry checks."""
    parsed = parse_recovery_id(recovery_id)
    if not parsed:
        raise LicenseError("That recovery ID does not look right.")
    return entitlement_from_response(
        await _post("/status", {"recovery_id": parsed, "app_id": APP_ID})
    )


def verify_offline(token: str) -> Entitlement:
    """Check a cached token without the network. Raises TokenError when the
    token is not proof of anything."""
    claims = verify_token(token, APP_ID)
    return Entitlement(
        status=str(claims.get("status") or "unknown"),
        product=str(claims.get("product") or ""),
        paid_through=claims.get("paid_through"),
        scope=str(claims.get("scope") or ""),
        token=token,
        offline=True,
    )


async def store_entitlement(storage, entitlement: Entitlement) -> None:
    """Persist the proof. The token is the proof; the flag is not."""
    if entitlement.recovery_id:
        await storage.set(constants.STORAGE_LICENSE_RECOVERY, entitlement.recovery_id)
    if entitlement.token:
        await storage.set(constants.STORAGE_LICENSE_TOKEN, entitlement.token)
    if entitlement.paid_through is not None:
        await storage.set(
            constants.STORAGE_LICENSE_PAID_THROUGH, str(entitlement.paid_through)
        )


async def cached_entitlement(storage) -> Entitlement | None:
    """What we can prove offline, if anything."""
    try:
        token = await storage.get(constants.STORAGE_LICENSE_TOKEN)
        if not token:
            return None
        return verify_offline(token)
    except TokenError as exc:
        logger.info("Cached license no longer valid: %s", exc)
        return None
    except Exception:
        logger.debug("Could not read cached license", exc_info=True)
        return None


async def apply_entitlement(entitlement: Entitlement) -> bool:
    """Move app state from an entitlement. Returns True when it grants.

    Only a definitive server ruling may clear an existing grant; anything
    else leaves the user exactly where they were. The status itself is
    always recorded so the renewal card can say "Payment overdue" rather
    than flattening everything into a boolean.
    """
    from core.state import state

    if entitlement.grants_access:
        state.is_premium = True
        state.premium_source = "kiri"
        state.premium_product = entitlement.product
        state.premium_offline = entitlement.offline
        state.premium_status = entitlement.status
        state.premium_paid_through = (
            float(entitlement.paid_through)
            if entitlement.paid_through is not None
            else None
        )
        return True
    if entitlement.is_definitive:
        state.is_premium = False
        state.premium_source = ""
        state.premium_product = ""
        state.premium_offline = False
        state.premium_status = entitlement.status
        state.premium_paid_through = (
            float(entitlement.paid_through)
            if entitlement.paid_through is not None
            else None
        )
    return False


__all__ = [
    "APP_ID",
    "BASE_URL",
    "Entitlement",
    "LicenseError",
    "Product",
    "apply_entitlement",
    "cached_entitlement",
    "check_status",
    "entitlement_from_response",
    "get_catalog",
    "parse_recovery_id",
    "restore",
    "start_checkout",
    "store_entitlement",
    "valid_email",
    "verify_offline",
]
