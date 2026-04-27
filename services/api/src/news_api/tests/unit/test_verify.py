"""Unit tests for ClerkClaims and InvalidKid."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from news_api.auth.verify import (
    ClerkClaims,
    InvalidKid,
    verify_clerk_jwt,
)


def test_clerk_claims_minimum_required():
    claims = ClerkClaims.model_validate(
        {
            "sub": "user_abc",
            "email": "alice@example.com",
            "name": "Alice Smith",
            "exp": 1_777_777_777,
            "iat": 1_777_777_000,
            "iss": "https://test.clerk.dev",
        }
    )
    assert claims.sub == "user_abc"
    assert claims.email == "alice@example.com"
    assert claims.name == "Alice Smith"
    assert claims.azp is None  # optional


def test_clerk_claims_rejects_invalid_email():
    with pytest.raises(ValidationError):
        ClerkClaims.model_validate(
            {
                "sub": "user_abc",
                "email": "not-an-email",
                "name": "Alice",
                "exp": 1_777_777_777,
                "iat": 1_777_777_000,
                "iss": "https://test.clerk.dev",
            }
        )


def test_invalid_kid_is_exception_subclass():
    assert issubclass(InvalidKid, Exception)
    raised = InvalidKid("kid 'foo' not in JWKS")
    assert "foo" in str(raised)


def _make_keypair(kid: str = "test-key-1"):
    privkey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pubkey = privkey.public_key()
    return privkey, {kid: pubkey}


def _sign(privkey, *, kid="test-key-1", **claim_overrides) -> str:
    claims = {
        "sub": "user_abc",
        "email": "alice@example.com",
        "name": "Alice",
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
        "iss": "https://test.clerk.dev",
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, privkey, algorithm="RS256", headers={"kid": kid})


def test_verify_clerk_jwt_happy_path():
    privkey, jwks = _make_keypair()
    token = _sign(privkey)
    claims = verify_clerk_jwt(token, jwks, issuer="https://test.clerk.dev", audience=None)
    assert isinstance(claims, ClerkClaims)
    assert claims.sub == "user_abc"


def test_verify_clerk_jwt_unknown_kid_raises_invalid_kid():
    privkey, jwks = _make_keypair(kid="other-key")
    token = _sign(privkey, kid="bogus-kid")
    with pytest.raises(InvalidKid):
        verify_clerk_jwt(token, jwks, issuer="https://test.clerk.dev", audience=None)


def test_verify_clerk_jwt_expired_raises_invalid_token():
    privkey, jwks = _make_keypair()
    token = _sign(privkey, exp=int(time.time()) - 60)
    with pytest.raises(jwt.ExpiredSignatureError):
        verify_clerk_jwt(token, jwks, issuer="https://test.clerk.dev", audience=None)


def test_verify_clerk_jwt_wrong_issuer_raises_invalid_token():
    privkey, jwks = _make_keypair()
    token = _sign(privkey, iss="https://attacker.example.com")
    with pytest.raises(jwt.InvalidIssuerError):
        verify_clerk_jwt(token, jwks, issuer="https://test.clerk.dev", audience=None)


def test_verify_clerk_jwt_rejects_hs256_attack():
    """Algorithm-confusion attack — HS256 forged with public key as shared secret.

    Defended by hard-coding ['RS256'] in the algorithm whitelist.
    """
    from cryptography.hazmat.primitives import serialization

    _, jwks = _make_keypair()
    pubkey_der = next(iter(jwks.values())).public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    forged = jwt.encode(
        {
            "sub": "user_abc",
            "email": "alice@example.com",
            "name": "A",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
            "iss": "https://test.clerk.dev",
        },
        pubkey_der,
        algorithm="HS256",
        headers={"kid": "test-key-1"},
    )
    with pytest.raises(jwt.InvalidAlgorithmError):
        verify_clerk_jwt(forged, jwks, issuer="https://test.clerk.dev", audience=None)
