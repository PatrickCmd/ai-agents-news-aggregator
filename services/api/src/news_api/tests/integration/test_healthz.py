import pytest

pytestmark = pytest.mark.asyncio


async def test_healthz_returns_ok(api_client):
    resp = await api_client.get("/v1/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "git_sha": "test-sha"}


async def test_healthz_does_not_require_auth(api_client):
    resp = await api_client.get("/v1/healthz")  # no Authorization header
    assert resp.status_code == 200
