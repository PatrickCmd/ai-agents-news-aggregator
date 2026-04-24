from news_config.settings import (
    AppSettings,
    DatabaseSettings,
    LangfuseSettings,
    OpenAISettings,
    ResendSettings,
    YouTubeProxySettings,
)


def test_database_settings_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://dev")
    monkeypatch.setenv("SUPABASE_POOLER_URL", "postgresql+asyncpg://pooler")
    s = DatabaseSettings()
    assert s.supabase_db_url == "postgresql+asyncpg://dev"
    assert s.supabase_pooler_url == "postgresql+asyncpg://pooler"


def test_openai_settings_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc")
    s = OpenAISettings()
    assert s.api_key == "sk-abc"
    assert s.is_configured is True


def test_openai_settings_not_configured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    s = OpenAISettings()
    assert s.is_configured is False


def test_langfuse_settings(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    s = LangfuseSettings()
    assert s.host == "https://cloud.langfuse.com"
    assert s.is_configured is True


def test_youtube_proxy_disabled_by_default(monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROXY_ENABLED", raising=False)
    s = YouTubeProxySettings()
    assert s.enabled is False
    assert s.is_configured is False


def test_resend_settings(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "r")
    s = ResendSettings()
    assert s.is_configured is True


def test_app_settings_defaults(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    s = AppSettings()
    assert s.env == "dev"
    assert s.log_level == "INFO"
