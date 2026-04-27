"""JWKS fetcher with a per-cold-start cache.

Module-level state ties cache lifetime to the Lambda container's lifetime —
new container = new cache, exactly what we want. Reset only fires in tests
or in response to a forced refresh (e.g., after a JWKS-rotation 401).
"""

from __future__ import annotations

from base64 import urlsafe_b64decode

import httpx
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPublicKey,
    RSAPublicNumbers,
)

_jwks: dict[str, RSAPublicKey] | None = None


def reset_jwks() -> None:
    """Drop the cache. Useful in tests and on forced JWKS refresh."""
    global _jwks
    _jwks = None


async def get_jwks(client: httpx.AsyncClient, url: str) -> dict[str, RSAPublicKey]:
    """Fetch + cache the JWKS for the container's life."""
    global _jwks
    if _jwks is None:
        resp = await client.get(url, timeout=5.0)
        resp.raise_for_status()
        _jwks = {k["kid"]: _rsa_pub_from_jwk(k) for k in resp.json()["keys"]}
    return _jwks


def _rsa_pub_from_jwk(jwk: dict) -> RSAPublicKey:
    """Convert a JWK to an RSA public key. Only RS256 keys are supported."""
    n = int.from_bytes(_b64u_decode(jwk["n"]), "big")
    e = int.from_bytes(_b64u_decode(jwk["e"]), "big")
    return RSAPublicNumbers(e=e, n=n).public_key()


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return urlsafe_b64decode(s + pad)
