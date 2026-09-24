"""ECDSA P-256 verification for Kiri License entitlement tokens.

The Worker signs with WebCrypto, and reproducing that exactly in Python needs
three details that are easy to get wrong and impossible to notice until a real
restore fails:

  - the signature is **raw r||s** (64 bytes for P-256), not DER
  - the signed message is the **base64url payload string** as UTF-8 bytes,
    not the decoded JSON
  - the public key is a base64url **SPKI DER** blob

We use `cryptography` for this. It is already a pinned dependency and already
listed in `[tool.flet.android] extract_packages`, so the wheel ships in the
APK — no new dependency, and no hand-rolled curve arithmetic.

Reference: kiri-license/src/token.js and src/entitlements.js.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

# Public verification key, safe to ship: it can confirm a signature, never
# produce one. Matches LICENSE_PUBLIC_KEY in the Worker's wrangler.toml.
PUBLIC_KEY = (
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE-YfZ-yKdG3wYF1IR0XcpJH4RclABnddMmAG"
    "XFI2J8sbC4gWY2POKc8hVrn0_uHxDZ9ufzwzg4buUimW-IEw4Uw"
)

ISSUER = "license.kiri.ng"
_SIGNATURE_BYTES = 64  # P-256 raw r||s


class TokenError(Exception):
    """The token is malformed, not signed by Kiri, or not valid here."""


def _b64url_decode(value: str) -> bytes:
    normalized = str(value).replace("-", "+").replace("_", "/")
    padded = normalized + "=" * ((4 - (len(normalized) % 4)) % 4)
    try:
        return base64.b64decode(padded)
    except (ValueError, TypeError) as exc:
        raise TokenError("invalid base64url") from exc


def _public_key(public_key: str = PUBLIC_KEY):
    try:
        return serialization.load_der_public_key(_b64url_decode(public_key))
    except TokenError:
        raise
    except Exception as exc:
        raise TokenError("unusable public key") from exc


def verify_token(
    token: str,
    app_id: str,
    public_key: str = PUBLIC_KEY,
    now: float | None = None,
) -> dict[str, Any]:
    """Verify a token and return its claims.

    Raises `TokenError` for anything that is not a valid entitlement for this
    app right now. Callers treat that as "not entitled", never as an error the
    user needs to see.
    """
    if not token or not isinstance(token, str):
        raise TokenError("empty token")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        raise TokenError("unrecognized token format")

    payload_b64, signature_b64 = parts[1], parts[2]
    raw_signature = _b64url_decode(signature_b64)
    if len(raw_signature) != _SIGNATURE_BYTES:
        raise TokenError("signature is not raw P-256 r||s")

    # WebCrypto signs the base64url payload *string*, so that is the message.
    message = payload_b64.encode("utf-8")
    # ...and it emits raw r||s, while `cryptography` verifies DER.
    r = int.from_bytes(raw_signature[:32], "big")
    s = int.from_bytes(raw_signature[32:], "big")
    der_signature = encode_dss_signature(r, s)

    try:
        _public_key(public_key).verify(
            der_signature, message, ec.ECDSA(hashes.SHA256())
        )
    except InvalidSignature as exc:
        raise TokenError("signature does not verify") from exc

    try:
        claims = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise TokenError("payload is not JSON") from exc
    if not isinstance(claims, dict):
        raise TokenError("payload is not an object")

    if claims.get("iss") != ISSUER:
        raise TokenError("issued by someone else")
    if claims.get("app") != app_id:
        raise TokenError("issued for a different app")
    if claims.get("status") not in ("active", "grace"):
        raise TokenError(f"not entitled: {claims.get('status')}")

    # `exp` is null for a lifetime license, which never expires.
    exp = claims.get("exp")
    if exp is not None:
        moment = time.time() if now is None else now
        if float(exp) <= moment:
            raise TokenError("token expired")
    return claims


__all__ = ["ISSUER", "PUBLIC_KEY", "TokenError", "verify_token"]
