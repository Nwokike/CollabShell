"""Offline verification of Kiri License entitlement tokens.

Verbatim port of ktv-player/src/services/license_token.py. Do not "improve"
the crypto here — the Worker signs what it signs, and any drift either breaks
verification or accepts a forged token. The tests in tests/test_license_token.py
run against real WebCrypto P-256 signatures (tests/license_fixtures.py), so a
transcription slip fails loudly rather than silently unlocking premium.

Trust model (kiri-license/docs/client-integration.md): the Worker is
authoritative whenever the app is online. The token is a signed cache that
keeps premium working offline, so a valid signature plus the claim checks
below are what unlock the app — never a bare client-side flag.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import math as _math
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# NIST P-256 (secp256r1) domain parameters.
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
_GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551

ISSUER = "license.kiri.ng"
_UNLOCKING_STATUSES = ("active", "grace")

# Attacker-controlled input bounds: an 8KB payload is already absurd for a
# claims object; anything bigger is a CPU/RAM DoS attempt, rejected before
# any crypto or parsing runs.
_MAX_PAYLOAD_B64 = 8192
_MAX_SIGNATURE_B64 = 200

# A P-256 SPKI is exactly 91 DER bytes: SEQUENCE + AlgorithmIdentifier
# (ecPublicKey + secp256r1 OIDs) + BIT STRING wrapping 0x04||X||Y.
_SPKI_LEN = 91
_SPKI_PREFIX = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d030107034200")

# Clock skew tolerance for future-issued tokens (device clocks drift).
_IAT_SKEW = 300


class TokenRejected(Exception):
    """The token is not a valid entitlement for this app."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}{': ' + detail if detail else ''}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class LicenseClaims:
    """The verified payload of an entitlement token."""

    ent: str
    app: str
    product: str
    scope: str
    mode: str
    status: str
    paid_through: int | None
    issued_at: int
    expires_at: int | None

    @property
    def is_lifetime(self) -> bool:
        return self.expires_at is None


def _b64url_decode(value: str) -> bytes:
    if not isinstance(value, str):
        raise TypeError("base64url value must be text")
    padded = value + "=" * ((-len(value)) % 4)
    return base64.b64decode(padded, altchars=b"-_", validate=True)


def _point_add(p1, p2):
    """Add two points on P-256 in affine coordinates; None is infinity.

    Returns False (not a point) when the math itself is undefined — a
    malformed Q must verify as bad_signature, never raise into the caller.
    """
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    try:
        x1, y1 = p1
        x2, y2 = p2
        if x1 == x2 and (y1 + y2) % _P == 0:
            return None
        if p1 == p2:
            lam = (3 * x1 * x1 + _A) * pow(2 * y1, -1, _P) % _P
        else:
            lam = (y2 - y1) * pow(x2 - x1, -1, _P) % _P
        x3 = (lam * lam - x1 - x2) % _P
        y3 = (lam * (x1 - x3) - y1) % _P
        return x3, y3
    except ValueError:
        return False


def _public_point_from_spki(public_key: str) -> tuple[int, int]:
    """Pull the uncompressed public point out of a base64url SPKI blob.

    Strict: exact 91 DER bytes, correct ecPublicKey/secp256r1 header, and
    coordinates in range — not the old suffix-only scan that accepted any
    blob ending in 0x04||X||Y.
    """
    if not isinstance(public_key, str):
        raise TokenRejected("bad_public_key", "public key must be text")
    try:
        der = _b64url_decode(public_key)
    except Exception as ex:  # binascii.Error, ValueError, TypeError
        raise TokenRejected("bad_public_key", "not valid base64url") from ex
    if len(der) != _SPKI_LEN or not der.startswith(_SPKI_PREFIX):
        raise TokenRejected("bad_public_key", "not a P-256 SPKI public key")
    x = int.from_bytes(der[-64:-32], "big")
    y = int.from_bytes(der[-32:], "big")
    if not (0 <= x < _P and 0 <= y < _P):
        raise TokenRejected("bad_public_key", "coordinates out of range")
    if (y * y - (x * x * x + _A * x + _B)) % _P != 0:
        raise TokenRejected("bad_public_key", "point is not on the curve")
    return x, y


def _ecdsa_verify(public_point, message: bytes, signature: bytes) -> bool:
    if len(signature) != 64:
        return False
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    if not (1 <= r < _N and 1 <= s < _N):
        return False
    digest = hashlib.sha256(message).digest()
    e = int.from_bytes(digest, "big")
    try:
        w = pow(s, -1, _N)
    except ValueError:
        return False
    u1 = e * w % _N
    u2 = r * w % _N
    try:
        point = _point_add(_scale((_GX, _GY), u1), _scale(public_point, u2))
    except ValueError, TypeError:
        return False
    if point is None or point is False:
        return False
    return point[0] % _N == r


def _scale(point, scalar: int):
    """k * P on P-256, using double-and-add."""
    if scalar % _N == 0 or point is None:
        return None
    result = None
    addend = point
    k = scalar
    while k:
        if k & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        k >>= 1
    return result


def _verify_signature(public_key: str, message: bytes, signature: bytes) -> bool:
    """Verify the Worker's raw r‖s signature (P-256 ECDSA over SHA-256).

    Dual contract: False for a bad signature, but TokenRejected propagates
    for a bad PUBLIC KEY (unparseable key, wrong curve) — callers
    distinguish "forged/wrong" from "misconfigured" by it.
    """
    if len(signature) != 64:
        return False
    return _ecdsa_verify(_public_point_from_spki(public_key), message, signature)


def _check_scope(scope, token_app, app_id: str) -> None:
    """Is this entitlement usable by *app_id*?

    Mirrors the Worker's ``scopeAllows`` (kiri-license/src/entitlements.js:61):
    a ``universal`` entitlement unlocks every app, so the ``app`` claim on the
    token is only a label of which app asked for it. A list scope is the only
    case that gates — the token's app must appear in it.

    This matters because the Worker re-mints a token per app on every restore
    (``issueEntitlement(config, record, body.app_id, ...)``), so a token minted
    while the license was universal is still valid when another app redeems the
    same recovery ID. Rejecting on an ``app`` mismatch would lock out a license
    the Worker says is universal.
    """
    if scope == "universal":
        return
    if isinstance(scope, list):
        # Only the REQUESTING app counts — exactly the Worker's scopeAllows.
        # Checking the token's own app too would let a ktv-player-scoped token
        # unlock here, which is precisely what a scope list exists to prevent.
        if app_id in scope:
            return
        raise TokenRejected("wrong_app", f"app={app_id!r} scope={scope!r}")
    # No scope claim at all: fall back to the token's own app, which is the
    # only thing an unscoped token can vouch for.
    if token_app != app_id:
        raise TokenRejected("wrong_app", f"app={app_id!r} token_app={token_app!r}")


def verify_token(
    token: str,
    public_key: str,
    app_id: str,
    *,
    now: float | None = None,
) -> LicenseClaims:
    """Verify a Kiri License token and return its claims.

    Raises TokenRejected with a machine-readable ``reason`` so the UI can say
    what went wrong (expired, revoked, not this app, bad signature) instead
    of a generic failure.
    """
    if not isinstance(token, str) or not token.strip():
        raise TokenRejected("missing_token")
    # Clipboard/file trailing newlines verify fine instead of bad_signature.
    token = token.strip()
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        raise TokenRejected("malformed_token")

    _, payload_b64, signature_b64 = parts
    if len(payload_b64) > _MAX_PAYLOAD_B64 or len(signature_b64) > _MAX_SIGNATURE_B64:
        raise TokenRejected("malformed_token", "segment too large")
    try:
        signature = _b64url_decode(signature_b64)
        payload_bytes = _b64url_decode(payload_b64)
    except (ValueError, TypeError) as ex:
        raise TokenRejected("malformed_token", str(ex)) from ex

    # WebCrypto signs the ASCII bytes of the base64url payload segment, not
    # the decoded JSON — matching that is what makes the signature verify.
    # Verify FIRST, parse second: unauthenticated JSON parsing of
    # attacker-controlled input is a DoS vector (huge payload → CPU/RAM).
    if not _verify_signature(public_key, payload_b64.encode("utf-8"), signature):
        logger.debug("Token signature check failed")
        raise TokenRejected("bad_signature")
    try:
        claims_raw = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as ex:
        raise TokenRejected("malformed_token", str(ex)) from ex
    if not isinstance(claims_raw, dict):
        raise TokenRejected("malformed_token", "payload is not an object")

    # Every numeric claim is validated here: a signed token carrying a
    # string or non-finite `exp` must be rejected as malformed, not raise
    # a ValueError/OverflowError into the settings handler.
    try:
        issued_at_raw = claims_raw.get("iat")
        expires_raw = claims_raw.get("exp")
        # `type(x) is int` (not isinstance): bool is int in Python, and
        # True must not pass as iat=1. NaN/Infinity arrive as float → out.
        if type(issued_at_raw) is not int:
            raise ValueError("iat must be an integer")
        if expires_raw is not None and type(expires_raw) is not int:
            raise ValueError("exp must be an integer or null")
    except ValueError as ex:
        raise TokenRejected("malformed_claims", str(ex)) from ex

    if claims_raw.get("iss") != ISSUER:
        raise TokenRejected("bad_issuer", str(claims_raw.get("iss")))
    _check_scope(claims_raw.get("scope"), claims_raw.get("app"), app_id)
    if type(claims_raw.get("v")) is not int or claims_raw.get("v") != 1:
        raise TokenRejected("unsupported_version", str(claims_raw.get("v")))

    if now is None:
        current = time.time()
    elif (
        isinstance(now, bool)
        or not isinstance(now, (int, float))
        or (isinstance(now, float) and not _math.isfinite(now))
    ):
        raise TokenRejected("malformed_claims", "now must be a finite number")
    else:
        current = now
    # Expiry first: time truth beats status text (an "active" token past exp
    # is expired, full stop).
    if expires_raw is not None and expires_raw <= current:
        raise TokenRejected("expired", str(expires_raw))

    raw_status = claims_raw.get("status")
    if raw_status not in _UNLOCKING_STATUSES:
        # Fixed reason + raw value in detail: the old str(status) made the
        # machine-readable reason attacker-shaped ("123", "{...}"), breaking
        # UI match arms and inviting log injection.
        raise TokenRejected("inactive_status", f"status={raw_status!r}")
    if issued_at_raw > current + _IAT_SKEW:
        raise TokenRejected("malformed_claims", "iat is in the future")
    if expires_raw is not None and expires_raw < issued_at_raw:
        raise TokenRejected("malformed_claims", "exp predates iat")
    nbf = claims_raw.get("nbf")
    if nbf is not None and (type(nbf) is not int or current < nbf):
        raise TokenRejected("not_yet_valid", f"nbf={nbf!r}")

    paid_through = claims_raw.get("paid_through")
    if paid_through is not None and type(paid_through) is not int:
        raise TokenRejected(
            "malformed_claims", "paid_through must be an integer or null"
        )

    ent = claims_raw.get("ent")
    product = claims_raw.get("product")
    if not isinstance(ent, str) or not ent:
        raise TokenRejected("malformed_claims", "missing ent")
    if not isinstance(product, str) or not product:
        raise TokenRejected("malformed_claims", "missing product")

    return LicenseClaims(
        ent=ent,
        app=str(claims_raw.get("app") or ""),
        product=product,
        scope=str(claims_raw.get("scope") or ""),
        mode=str(claims_raw.get("mode") or ""),
        status=raw_status,
        paid_through=paid_through,
        issued_at=issued_at_raw,
        expires_at=expires_raw,
    )
