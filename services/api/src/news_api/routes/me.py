"""User identity routes — GET /me, PUT /me/profile (PUT in Task 4.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from news_schemas.user_profile import UserOut

from news_api.deps import get_current_user

router = APIRouter()


@router.get("/me", response_model=UserOut)
async def get_me(current_user: UserOut = Depends(get_current_user)) -> UserOut:  # noqa: B008
    return current_user
