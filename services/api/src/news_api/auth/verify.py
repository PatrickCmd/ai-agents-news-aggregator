"""Clerk JWT verification primitives.

Exposes:
    ClerkClaims — Pydantic model of the JWT payload we care about.
    InvalidKid — raised when the JWT's `kid` header is not in the cached JWKS.
    verify_clerk_jwt — pure function (added in Task 3.3).
"""

from __future__ import annotations

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from pydantic import BaseModel, ConfigDict, EmailStr


class InvalidKid(Exception):  # noqa: N818
    """Token's kid header doesn't match any cached JWK."""


class ClerkClaims(BaseModel):
    """Subset of Clerk's JWT payload that we use.

    Clerk's JWT can carry many more claims (org_id, session_id, etc.); we
    only validate the ones the API needs. Extra fields are ignored, not
    forbidden — Clerk will add fields over time.
    """

    model_config = ConfigDict(extra="ignore")

    sub: str
    email: EmailStr
    name: str
    exp: int
    iat: int
    iss: str
    azp: str | None = None


def verify_clerk_jwt(
    token: str,
    jwks: dict[str, RSAPublicKey],
    issuer: str,
    audience: str | None,
) -> ClerkClaims:
    """Validate a Clerk-issued JWT.

    Args:
        token: The raw JWT string from the `Authorization: Bearer <token>` header.
        jwks: Map of `kid` → RSA public key, populated by `auth.jwks.get_jwks`.
        issuer: Expected `iss` claim — must match exactly.
        audience: Expected `aud` claim, or `None` to skip validation.

    Raises:
        InvalidKid: The token's kid header is not in the JWKS.
        jwt.InvalidTokenError (and subclasses): signature, issuer, audience,
            or expiration check failed.
    """
    headers = jwt.get_unverified_header(token)
    kid = headers.get("kid")
    if kid is None or kid not in jwks:
        raise InvalidKid(f"kid {kid!r} not in JWKS")
    payload = jwt.decode(
        token,
        jwks[kid],
        algorithms=["RS256"],  # whitelist defeats algorithm-confusion attacks
        issuer=issuer,
        audience=audience,
        options={"require": ["exp", "iat", "iss", "sub"]},
    )
    return ClerkClaims.model_validate(payload)
