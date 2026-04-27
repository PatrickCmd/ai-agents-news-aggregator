"""Digest list + detail routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from news_db.repositories.digest_repo import DigestRepository
from news_schemas.digest import DigestOut, DigestSummaryOut
from news_schemas.user_profile import UserOut
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from news_api.deps import get_current_user, get_session_dep

router = APIRouter()


class DigestListResponse(BaseModel):
    items: list[DigestSummaryOut]
    next_before: int | None


@router.get("/digests", response_model=DigestListResponse)
async def list_digests(
    limit: int = Query(default=10, ge=1, le=50),
    before: int | None = Query(default=None, ge=1),
    current_user: UserOut = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session_dep),  # noqa: B008
) -> DigestListResponse:
    repo = DigestRepository(session)
    items = await repo.get_for_user(current_user.id, limit=limit, before=before)
    next_before = items[-1].id if len(items) == limit else None
    return DigestListResponse(items=items, next_before=next_before)


@router.get("/digests/{digest_id}", response_model=DigestOut)
async def get_digest(
    digest_id: int,
    current_user: UserOut = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session_dep),  # noqa: B008
) -> DigestOut:
    repo = DigestRepository(session)
    digest = await repo.get_by_id(digest_id)
    # Same 404 for nonexistent and not-mine — don't leak existence.
    if digest is None or digest.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "digest not found")
    return digest
