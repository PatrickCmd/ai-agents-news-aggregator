"""Clerk JWT verification primitives.

Exposes:
    ClerkClaims — Pydantic model of the JWT payload we care about.
    InvalidKid — raised when the JWT's `kid` header is not in the cached JWKS.
    verify_clerk_jwt — pure function (added in Task 3.3).
"""

from __future__ import annotations

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
