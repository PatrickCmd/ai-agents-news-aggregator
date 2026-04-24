from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from news_db.engine import get_session
from news_db.repositories.scraper_run_repo import ScraperRunRepository
from news_scraper.main import create_app
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_healthz_returns_ok(session: AsyncSession) -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_post_ingest_creates_run_row(session: AsyncSession) -> None:
    async def _noop(**kwargs: object) -> None:
        return None

    with patch("news_scraper.api.routes._run_background", side_effect=_noop):
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/ingest", json={"lookback_hours": 12, "trigger": "api"})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "running"
    assert body["lookback_hours"] == 12
    assert set(body["pipelines_requested"]) == {"youtube", "rss", "web_search"}

    async with get_session() as s:
        repo = ScraperRunRepository(s)
        row = await repo.get_by_id(body["id"])
        assert row is not None
        assert row.status.value == "running"


@pytest.mark.asyncio
async def test_runs_endpoint_lists_recent(session: AsyncSession) -> None:
    async def _noop(**kwargs: object) -> None:
        return None

    with patch("news_scraper.api.routes._run_background", side_effect=_noop):
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            for _ in range(2):
                resp = await ac.post("/ingest/rss", json={})
                assert resp.status_code == 202

            resp = await ac.get("/runs?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
