"""Integration test fixtures: ASGI client + monkeypatched settings.

`api_client` depends on `pg_container` from the shared
tests/integration/conftest.py — that fixture boots Postgres in Docker,
sets SUPABASE_* env vars, and runs Alembic. Session-scoped so the cost
is paid once per test session, even though /healthz doesn't need DB.

The JWT keypair / signed_jwt / patch_jwks fixtures land in Task 4.2
when get_current_user arrives.
"""

from __future__ import annotations

import time

import jwt as pyjwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
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


@pytest.fixture(scope="session")
def jwt_keypair():
    """One RSA keypair per test session — used to sign tokens locally."""
    privkey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return privkey, privkey.public_key()


@pytest.fixture(autouse=True)
def patch_jwks(monkeypatch, jwt_keypair):
    """Replace the JWKS fetcher to return the test public key."""
    _, pubkey = jwt_keypair

    async def _fake_get_jwks(*_args, **_kwargs):
        return {"test-key-1": pubkey}

    from news_api.auth import jwks as jwks_module

    monkeypatch.setattr(jwks_module, "get_jwks", _fake_get_jwks)
    jwks_module.reset_jwks()


@pytest.fixture
def signed_jwt(jwt_keypair):
    privkey, _ = jwt_keypair

    def _sign(
        *,
        sub: str,
        email: str,
        name: str = "Test User",
        issuer: str = "https://test.clerk.dev",
        expires_in: int = 600,
    ) -> str:
        return pyjwt.encode(
            {
                "sub": sub,
                "email": email,
                "name": name,
                "iat": int(time.time()),
                "exp": int(time.time()) + expires_in,
                "iss": issuer,
            },
            privkey,
            algorithm="RS256",
            headers={"kid": "test-key-1"},
        )

    return _sign


@pytest.fixture
def auth_header(signed_jwt):
    """Convenience: returns a function that produces an Authorization header dict."""

    def _header(*, sub: str, email: str = "alice@example.com", name: str = "Alice") -> dict:
        return {"Authorization": f"Bearer {signed_jwt(sub=sub, email=email, name=name)}"}

    return _header
