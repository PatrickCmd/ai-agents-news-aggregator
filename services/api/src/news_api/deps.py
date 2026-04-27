"""FastAPI dependencies: DB session, audit logger, current user."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from news_db.engine import get_session
from news_db.repositories.audit_log_repo import AuditLogRepository
from news_db.repositories.user_repo import UserRepository
from news_observability.audit import AuditLogger
from news_schemas.user_profile import UserIn, UserOut, UserProfile
from sqlalchemy.ext.asyncio import AsyncSession

from news_api.auth.jwks import get_jwks
from news_api.auth.verify import InvalidKid, verify_clerk_jwt
from news_api.settings import get_api_settings

# Single httpx client per process — reused across requests for connection
# pooling. Lambda containers run one request at a time so this is safe.
_http_client = httpx.AsyncClient(timeout=5.0)


async def get_session_dep() -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession scoped to the current request."""
    async with get_session() as session:
        yield session


def get_audit_logger(
    session: AsyncSession = Depends(get_session_dep),  # noqa: B008
) -> AuditLogger:
    """AuditLogger bound to the current request's DB session."""
    return AuditLogger(AuditLogRepository(session).insert)


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session_dep),  # noqa: B008
) -> UserOut:
    """Validate Clerk JWT and return (or lazy-create) the matching user.

    Sequence:
        1. Read Authorization: Bearer <token>.
        2. Ensure JWKS is cached for this container (lazy fetch).
        3. Verify signature + iss/exp/iat/sub against the cached JWK.
        4. Look up users.clerk_user_id; if missing, upsert from JWT claims.
    """
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth[7:]

    settings = get_api_settings()
    try:
        jwks = await get_jwks(_http_client, settings.clerk_jwks_url)
        claims = verify_clerk_jwt(token, jwks, settings.clerk_issuer, audience=None)
    except (InvalidKid, jwt.InvalidTokenError):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    repo = UserRepository(session)
    user = await repo.get_by_clerk_id(claims.sub)
    if user is not None:
        return user

    # Lazy upsert: first authenticated request from this Clerk user.
    return await repo.upsert_by_clerk_id(
        UserIn(
            clerk_user_id=claims.sub,
            email=claims.email,
            name=claims.name,
            email_name=claims.name.split()[0] if claims.name else "there",
            profile=UserProfile.empty(),
            profile_completed_at=None,
        )
    )
