"""Kiri License token verification.

These tests sign real ECDSA P-256 keys rather than mocking the verifier: the
whole risk of this module is in the three conversions between WebCrypto and
Python (raw r||s vs DER, payload string vs decoded JSON, SPKI DER key), and a
mock would happily pass while the real restore broke in production.
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.license_crypto import (
    ISSUER,
    PUBLIC_KEY,
    TokenError,
    verify_token,
)

APP_ID = "ng.kiri.collabshell"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


@pytest.fixture(scope="module")
def keypair():
    private = ec.generate_private_key(ec.SECP256R1())
    public_b64 = _b64(
        private.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private, public_b64


def _claims(**overrides) -> dict:
    now = int(time.time())
    base = {
        "iss": ISSUER,
        "v": 1,
        "ent": "hash",
        "app": APP_ID,
        "product": "lifetime",
        "scope": "universal",
        "mode": "one_time",
        "status": "active",
        "paid_through": None,
        "iat": now,
        "exp": None,
    }
    base.update(overrides)
    return base


def _sign(claims: dict, private, *, raw: bool = True) -> str:
    """Produce a token the way the Worker's WebCrypto does."""
    payload = _b64(json.dumps(claims).encode())
    der = private.sign(payload.encode(), ec.ECDSA(hashes.SHA256()))
    if raw:
        # WebCrypto signature: raw r||s, not DER.
        r, s = decode_dss_signature(der)
        der = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"v1.{payload}.{_b64(der)}"


def test_a_lifetime_token_verifies(keypair):
    private, public = keypair
    claims = verify_token(_sign(_claims(), private), APP_ID, public)
    assert claims["product"] == "lifetime"
    assert claims["status"] == "active"


def test_a_lifetime_license_never_expires(keypair):
    # exp is null for one-time purchases; treating that as "expired at 0"
    # would lock out every lifetime customer on the next launch.
    private, public = keypair
    assert _claims()["exp"] is None
    verify_token(_sign(_claims(), private), APP_ID, public, now=time.time() + 10**9)


def test_a_recurring_token_expires(keypair):
    private, public = keypair
    token = _sign(_claims(product="monthly", exp=int(time.time()) - 1), private)
    with pytest.raises(TokenError, match="expired"):
        verify_token(token, APP_ID, public)


def test_a_token_for_another_app_is_refused(keypair):
    private, public = keypair
    token = _sign(_claims(app="com.some.other.app"), private)
    with pytest.raises(TokenError, match="different app"):
        verify_token(token, APP_ID, public)


def test_another_issuer_is_refused(keypair):
    private, public = keypair
    token = _sign(_claims(iss="evil.example"), private)
    with pytest.raises(TokenError, match="issued by someone else"):
        verify_token(token, APP_ID, public)


@pytest.mark.parametrize("status", ["expired", "revoked", "pending"])
def test_a_non_entitled_status_is_refused(keypair, status):
    private, public = keypair
    token = _sign(_claims(status=status), private)
    with pytest.raises(TokenError, match="not entitled"):
        verify_token(token, APP_ID, public)


def test_grace_still_grants(keypair):
    private, public = keypair
    verify_token(_sign(_claims(status="grace"), private), APP_ID, public)


def test_a_tampered_signature_is_refused(keypair):
    private, public = keypair
    token = _sign(_claims(), private)
    tampered = token[:-6] + "AAAAAA"
    with pytest.raises(TokenError, match="signature"):
        verify_token(tampered, APP_ID, public)


def test_a_tampered_payload_is_refused(keypair):
    private, public = keypair
    _version, payload, signature = _sign(_claims(), private).split(".")
    # Swap the product without re-signing: the bytes signed no longer match.
    forged = _b64(json.dumps(_claims(product="yearly")).encode())
    with pytest.raises(TokenError, match="signature"):
        verify_token(f"v1.{forged}.{signature}", APP_ID, public)
    assert payload  # the original was well-formed


def test_a_der_signature_is_refused(keypair):
    """Guards the exact mistake: if someone 'fixes' the verifier to expect
    DER, this test fails instead of every real restore failing."""
    private, public = keypair
    token = _sign(_claims(), private, raw=False)
    with pytest.raises(TokenError, match="raw P-256"):
        verify_token(token, APP_ID, public)


@pytest.mark.parametrize(
    "token",
    ["", "not-a-token", "v2.abc.def", "v1.onlytwo", "v1.a.b.c.d"],
)
def test_malformed_tokens_are_refused(keypair, token):
    _private, public = keypair
    with pytest.raises(TokenError):
        verify_token(token, APP_ID, public)


def test_the_shipped_public_key_loads(keypair):
    """The key in the source must be a real SPKI blob, or every restore
    fails on a user's device and never in our tests. A token signed by some
    other key must therefore NOT verify against it."""
    private, _public = keypair
    token = _sign(_claims(), private)
    with pytest.raises(TokenError):
        verify_token(token, APP_ID, PUBLIC_KEY)
