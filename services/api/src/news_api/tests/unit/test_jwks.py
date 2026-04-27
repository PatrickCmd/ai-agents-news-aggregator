"""Unit tests for the JWKS cache."""

from __future__ import annotations

from base64 import urlsafe_b64encode

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from news_api.auth import jwks as jwks_module


def _b64u(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return urlsafe_b64encode(raw).rstrip(b"=").decode()


def _public_jwk(pubkey, *, kid: str = "key-1") -> dict:
    nums = pubkey.public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64u(nums.n),
        "e": _b64u(nums.e),
    }


def _jwks_payload(*pubkeys_with_kids) -> dict:
    return {"keys": [_public_jwk(p, kid=k) for p, k in pubkeys_with_kids]}


@pytest.fixture(autouse=True)
def _reset():
    jwks_module.reset_jwks()
    yield
    jwks_module.reset_jwks()


async def test_get_jwks_fetches_once_and_caches():
    pub = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    payload = _jwks_payload((pub, "key-1"))

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        out1 = await jwks_module.get_jwks(client, "https://test/jwks")
        out2 = await jwks_module.get_jwks(client, "https://test/jwks")

    assert isinstance(out1["key-1"], RSAPublicKey)
    assert out1 is out2  # cached identity


async def test_reset_jwks_forces_refresh():
    pub1 = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    pub2 = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    payloads = iter([_jwks_payload((pub1, "key-1")), _jwks_payload((pub2, "key-2"))])

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(payloads))

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        first = await jwks_module.get_jwks(client, "https://test/jwks")
        assert "key-1" in first
        jwks_module.reset_jwks()
        second = await jwks_module.get_jwks(client, "https://test/jwks")
        assert "key-2" in second
        assert "key-1" not in second
