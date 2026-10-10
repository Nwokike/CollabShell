"""Token verifier tests, against real ECDSA P-256 signatures.

The fixtures in tests/license_fixtures.py are minted by Node WebCrypto from a
throwaway keypair — the same code path the license Worker uses — so these
exercise genuine signatures rather than vectors this suite invented. A port
slip in the verifier fails here instead of silently unlocking premium.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

# Only src/ goes on the path. tests/ must NOT: tests/services/ is a package
# whose name would shadow src/services/ for every `import services.*`.
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Load the fixtures by path rather than by module name, for the same reason.
_spec = importlib.util.spec_from_file_location(
    "license_fixtures", _HERE / "license_fixtures.py"
)
_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixtures)
PUBLIC_KEY = _fixtures.PUBLIC_KEY
TOKENS = _fixtures.TOKENS

from services.license_token import (
    LicenseClaims,
    TokenRejected,
    verify_token,
)

APP = "ng.kiri.collabshell"
NOW = 1758600000  # matches the fixtures' iat, so nothing is "in the future"


def _verify(name, app=APP, now=NOW, key=PUBLIC_KEY):
    return verify_token(TOKENS[name], key, app, now=now)


# ── the happy paths ────────────────────────────────────────────────────────


def test_lifetime_token_verifies():
    claims = _verify("LIFETIME")
    assert claims.status == "active"
    assert claims.is_lifetime is True
    assert claims.expires_at is None
    assert claims.app == APP
    assert claims.product == "lifetime"
    assert claims.scope == "universal"


def test_recurring_token_reports_its_expiry():
    claims = _verify("YEARLY_ACTIVE")
    assert claims.is_lifetime is False
    assert claims.expires_at == 4102444800  # 2100-01-01
    assert claims.mode == "recurring"
    assert claims.paid_through == 4102444800


def test_grace_period_still_unlocks():
    claims = _verify("GRACE")
    assert claims.status == "grace"


def test_verified_claims_are_frozen():
    """Verified claims must not be mutable by a caller — the whole point of a
    frozen dataclass here is that nothing downstream can re-write a status."""
    import dataclasses

    claims = _verify("LIFETIME")
    assert isinstance(claims, LicenseClaims)
    with pytest.raises(dataclasses.FrozenInstanceError):
        claims.status = "revoked"


# ── rejection reasons (each names WHY) ─────────────────────────────────────


@pytest.mark.parametrize(
    "name,reason",
    [
        ("EXPIRED", "expired"),
        ("REVOKED", "inactive_status"),
        ("SCOPED_OUT", "wrong_app"),
        ("BAD_ISSUER", "bad_issuer"),
        ("UNSUPPORTED_VERSION", "unsupported_version"),
    ],
)
def test_rejected_tokens_name_their_reason(name, reason):
    with pytest.raises(TokenRejected) as info:
        _verify(name)
    assert info.value.reason == reason


def test_revoked_status_detail_names_the_status():
    with pytest.raises(TokenRejected) as info:
        _verify("REVOKED")
    assert "revoked" in info.value.detail


def test_expiry_beats_status_text():
    """An 'active' token past exp is expired — time truth, not status text."""
    with pytest.raises(TokenRejected) as info:
        verify_token(TOKENS["EXPIRED"], PUBLIC_KEY, APP, now=1758600000)
    assert info.value.reason == "expired"


def test_expiry_is_evaluated_against_the_current_time():
    # Exactly at exp is expired (`<=`), one second before is not. Both use an
    # explicit now so the assertion does not drift with the real clock.
    token = TOKENS["YEARLY_ACTIVE"]
    assert verify_token(token, PUBLIC_KEY, APP, now=4102444799).status == "active"
    with pytest.raises(TokenRejected) as info:
        verify_token(token, PUBLIC_KEY, APP, now=4102444800)
    assert info.value.reason == "expired"


# ── forgery and key handling ───────────────────────────────────────────────


def test_tampered_payload_is_rejected():
    token = TOKENS["LIFETIME"]
    head, payload, sig = token.split(".")
    # Flip the status inside the signed payload.
    import base64
    import json

    raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    claims = json.loads(raw)
    claims["status"] = "active"
    claims["ent"] = "stolen"
    forged = (
        base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    )
    with pytest.raises(TokenRejected) as info:
        verify_token(f"{head}.{forged}.{sig}", PUBLIC_KEY, APP)
    assert info.value.reason == "bad_signature"


def test_universal_scope_unlocks_every_app():
    """The Worker's own rule (scopeAllows): universal means every app.

    Every Kiri product carries scope "universal", and the Worker re-mints a
    token with the REQUESTING app's id on restore — so a token stamped for
    ktv-player is a valid entitlement here too. Rejecting on an app mismatch
    would lock out a licence the Worker says is universal.
    """
    claims = _verify("OTHER_APP")
    assert claims.status == "active"
    assert claims.scope == "universal"
    assert claims.app == "ng.kiri.ktvplayer"


def test_a_scope_list_is_the_only_gate():
    """A per-app scope list does gate — and nothing else does."""
    with pytest.raises(TokenRejected) as info:
        _verify("SCOPED_OUT")
    assert info.value.reason == "wrong_app"
    # The same token is fine for the app that owns the scope.
    assert _verify("SCOPED_OUT", app="ng.kiri.ktvplayer").status == "active"


def test_a_missing_scope_falls_back_to_the_tokens_app():
    """An unscoped token can only vouch for the app it names.

    Asserted through the scope check directly: re-signing a token with the
    fixture's private key is impossible here (the minting script discards it),
    and the check IS the rule.
    """
    from services.license_token import _check_scope

    with pytest.raises(TokenRejected) as info:
        _check_scope(None, "ng.kiri.ktvplayer", APP)
    assert info.value.reason == "wrong_app"

    # A matching app passes the fallback.
    _check_scope(None, APP, APP)
    # An empty list scope never grants.
    with pytest.raises(TokenRejected):
        _check_scope([], "anything", APP)


def test_universal_scope_ignores_the_app_claim():
    """The Worker's own rule: universal means every app, no exceptions."""
    from services.license_token import _check_scope

    _check_scope("universal", "ng.kiri.ktvplayer", APP)
    _check_scope("universal", "com.unrelated.app", APP)


def test_token_from_another_key_is_rejected():
    """A validly signed token from a DIFFERENT keypair is a bad signature.

    Note the dual contract: `bad_public_key` is reserved for a key that does
    not parse as a P-256 SPKI point at all (tested separately). The production
    Worker key parses fine, so a signature made by another keypair simply
    fails to verify — which is the stronger, more common failure.
    """
    with pytest.raises(TokenRejected) as info:
        verify_token(
            TOKENS["LIFETIME"],
            "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE-YfZ-yKdG3wYF1IR0XcpJH4RclAB"
            "nddMmAGXFI2J8sbC4gWY2POKc8hVrn0_uHxDZ9ufzwzg4buUimW-IEw4Uw",
            APP,
        )
    assert info.value.reason == "bad_signature"


def test_production_public_key_is_a_valid_p256_key():
    """The shipped Worker key parses as a real P-256 SPKI point."""
    from services.license_token import _public_point_from_spki

    point = _public_point_from_spki(
        "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE-YfZ-yKdG3wYF1IR0XcpJH4RclAB"
        "nddMmAGXFI2J8sbC4gWY2POKc8hVrn0_uHxDZ9ufzwzg4buUimW-IEw4Uw"
    )
    x, y = point
    assert 0 < x < (1 << 256) and 0 < y < (1 << 256)


def test_signature_is_the_raw_webcrypto_pair():
    """The signature segment is 64 raw bytes (r||s), not ASN.1 DER."""
    import base64

    _head, _payload, sig = TOKENS["LIFETIME"].split(".")
    raw = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
    assert len(raw) == 64


# ── malformed input ────────────────────────────────────────────────────────


def test_malformed_tokens_are_rejected():
    for bad in ("", "   ", "v1", "v1.only", "v1.two.three", "x1.a.b"):
        with pytest.raises(TokenRejected) as info:
            verify_token(bad, PUBLIC_KEY, APP)
        assert info.value.reason in ("missing_token", "malformed_token"), bad


def test_trailing_newline_still_verifies():
    """A clipboard copy carries a newline; that must not be bad_signature."""
    claims = verify_token(TOKENS["LIFETIME"] + "\n", PUBLIC_KEY, APP)
    assert claims.status == "active"


def test_non_string_token_is_rejected():
    for bad in (None, 123, b"v1.a.b"):
        with pytest.raises(TokenRejected) as info:
            verify_token(bad, PUBLIC_KEY, APP)
        assert info.value.reason == "missing_token"


def test_oversized_segments_are_rejected_before_crypto():
    with pytest.raises(TokenRejected) as info:
        verify_token("v1." + "A" * 9000 + ".AAAA", PUBLIC_KEY, APP)
    assert info.value.reason == "malformed_token"
    assert "segment too large" in info.value.detail


def test_bad_base64_signature_is_malformed():
    with pytest.raises(TokenRejected) as info:
        verify_token("v1." + "A" * 40 + ".!!!not-b64!!!", PUBLIC_KEY, APP)
    assert info.value.reason == "malformed_token"


def test_bad_public_key_is_rejected():
    for bad in ("", "!!!", "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE"):
        with pytest.raises(TokenRejected) as info:
            verify_token(TOKENS["LIFETIME"], bad, APP)
        assert info.value.reason == "bad_public_key", bad


# ── clock and claim typing ─────────────────────────────────────────────────


def test_verification_uses_wall_clock_when_now_is_omitted():
    # No `now` -> time.time(); the fixtures' exp is in the future for that.
    claims = verify_token(TOKENS["YEARLY_ACTIVE"], PUBLIC_KEY, APP)
    assert claims.status == "active"


def test_v_true_is_not_a_version():
    """bool is int in Python; True must not pass as v=1."""
    import base64
    import json

    _head, payload, sig = TOKENS["LIFETIME"].split(".")
    raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    claims = json.loads(raw)
    claims["v"] = True
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    # The signature no longer matches, so this is rejected as bad_signature
    # rather than reaching the version check — which is the stronger outcome.
    with pytest.raises(TokenRejected) as info:
        verify_token(f"v1.{forged}.{sig}", PUBLIC_KEY, APP)
    assert info.value.reason == "bad_signature"


@pytest.mark.parametrize("bad", ["x", float("nan"), float("inf"), True])
def test_bad_now_is_rejected(bad):
    """`now=None` is NOT here: it is the documented wall-clock sentinel."""
    with pytest.raises(TokenRejected) as info:
        verify_token(TOKENS["LIFETIME"], PUBLIC_KEY, APP, now=bad)
    assert info.value.reason == "malformed_claims"
    assert "now" in info.value.detail


def test_valid_now_types_are_accepted():
    assert verify_token(TOKENS["LIFETIME"], PUBLIC_KEY, APP, now=1758600000.5)
    assert verify_token(TOKENS["LIFETIME"], PUBLIC_KEY, APP, now=1758600000)


def test_future_iat_is_rejected():
    with pytest.raises(TokenRejected) as info:
        _verify("LIFETIME", now=1758600000 - 1000)
    assert info.value.reason == "malformed_claims"
    assert "future" in info.value.detail
