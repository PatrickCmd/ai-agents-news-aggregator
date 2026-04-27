"""ApiSettings env loading."""

from news_api.settings import ApiSettings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("CLERK_ISSUER", "https://test.clerk.dev")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://test.clerk.dev/.well-known/jwks.json")
    monkeypatch.setenv(
        "REMIX_STATE_MACHINE_ARN",
        "arn:aws:states:us-east-1:111111111111:stateMachine:news-remix-user-dev",
    )
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000,https://example.com")
    monkeypatch.setenv("GIT_SHA", "abc123")

    s = ApiSettings()
    assert s.clerk_issuer == "https://test.clerk.dev"
    assert s.clerk_jwks_url == "https://test.clerk.dev/.well-known/jwks.json"
    assert s.remix_state_machine_arn.endswith(":news-remix-user-dev")
    assert s.allowed_origins == ["http://localhost:3000", "https://example.com"]
    assert s.git_sha == "abc123"


def test_settings_allowed_origins_defaults_to_localhost(monkeypatch):
    monkeypatch.setenv("CLERK_ISSUER", "https://test.clerk.dev")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://test.clerk.dev/.well-known/jwks.json")
    monkeypatch.setenv(
        "REMIX_STATE_MACHINE_ARN",
        "arn:aws:states:us-east-1:111111111111:stateMachine:news-remix-user-dev",
    )
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)

    s = ApiSettings()
    assert s.allowed_origins == ["http://localhost:3000"]
