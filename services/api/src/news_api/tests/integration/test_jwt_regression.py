"""End-to-end JWT-validation regressions: tampered, wrong issuer/algorithm, missing kid."""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization

pytestmark = pytest.mark.asyncio


async def test_wrong_issuer_returns_401(api_client, jwt_keypair):
    privkey, _ = jwt_keypair
    token = jwt.encode(
        {
            "sub": "user_x",
            "email": "x@x.com",
            "name": "X",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
            "iss": "https://attacker.example.com",
        },
        privkey,
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )
    resp = await api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_tampered_signature_returns_401(api_client, signed_jwt):
    token = signed_jwt(sub="user_x", email="x@x.com", name="X")
    # Flip the last character of the signature segment.
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    resp = await api_client.get("/v1/me", headers={"Authorization": f"Bearer {tampered}"})
    assert resp.status_code == 401


async def test_missing_kid_returns_401(api_client, jwt_keypair):
    privkey, _ = jwt_keypair
    token = jwt.encode(
        {
            "sub": "user_x",
            "email": "x@x.com",
            "name": "X",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
            "iss": "https://test.clerk.dev",
        },
        privkey,
        algorithm="RS256",
        # no headers={"kid": ...}
    )
    resp = await api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_hs256_forgery_returns_401(api_client, jwt_keypair):
    """Algorithm-confusion: forge HS256 with public key bytes as shared secret."""
    _, pubkey = jwt_keypair
    pubkey_der = pubkey.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    forged = jwt.encode(
        {
            "sub": "user_x",
            "email": "x@x.com",
            "name": "X",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
            "iss": "https://test.clerk.dev",
        },
        pubkey_der,
        algorithm="HS256",
        headers={"kid": "test-key-1"},
    )
    resp = await api_client.get("/v1/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401
