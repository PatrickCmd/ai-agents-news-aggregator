"""Integration test fixtures: ASGI client + monkeypatched settings.

`api_client` depends on `pg_container` from the shared
tests/integration/conftest.py — that fixture boots Postgres in Docker,
sets SUPABASE_* env vars, and runs Alembic. Session-scoped so the cost
is paid once per test session, even though /healthz doesn't need DB.

The JWT keypair / signed_jwt / patch_jwks fixtures land in Task 4.2
when get_current_user arrives.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from testcontainers.postgres import PostgresContainer


@pytest.fixture
def api_settings_env(monkeypatch):
    monkeypatch.setenv("CLERK_ISSUER", "https://test.clerk.dev")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://test.clerk.dev/.well-known/jwks.json")
    monkeypatch.setenv(
        "REMIX_STATE_MACHINE_ARN",
        "arn:aws:states:us-east-1:111111111111:stateMachine:news-remix-user-dev",
    )
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("GIT_SHA", "test-sha")
    from news_api.settings import get_api_settings

    get_api_settings.cache_clear()


@pytest_asyncio.fixture
async def api_client(api_settings_env, pg_container: PostgresContainer):
    """ASGI client wired to the testcontainer Postgres."""
    from news_db import engine as engine_module

    from news_api.app import create_app

    engine_module.reset_engine()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    engine_module.reset_engine()
