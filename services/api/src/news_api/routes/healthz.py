"""Health probe — no auth, returns deploy-time git_sha."""

from __future__ import annotations

from fastapi import APIRouter

from news_api.settings import get_api_settings

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "git_sha": get_api_settings().git_sha}
