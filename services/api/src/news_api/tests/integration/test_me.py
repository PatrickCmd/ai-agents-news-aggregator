import pytest

pytestmark = pytest.mark.asyncio


async def test_me_requires_bearer(api_client):
    resp = await api_client.get("/v1/me")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


async def test_me_rejects_invalid_token(api_client):
    resp = await api_client.get("/v1/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


async def test_me_lazy_creates_user_on_first_call(api_client, auth_header):
    resp = await api_client.get(
        "/v1/me",
        headers=auth_header(sub="user_first", email="first@x.com", name="First User"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["clerk_user_id"] == "user_first"
    assert body["email"] == "first@x.com"
    assert body["name"] == "First User"
    assert body["email_name"] == "First"
    assert body["profile_completed_at"] is None
    # Profile is the empty default.
    assert body["profile"]["interests"]["primary"] == []


async def test_me_returns_existing_user_on_second_call(api_client, auth_header):
    h = auth_header(sub="user_second", email="second@x.com", name="Second")
    first = await api_client.get("/v1/me", headers=h)
    second = await api_client.get("/v1/me", headers=h)
    assert first.status_code == 200
    assert second.status_code == 200
    # Same DB row.
    assert first.json()["id"] == second.json()["id"]
