from news_observability.tracing import configure_tracing


def test_configure_tracing_is_idempotent(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    # No Langfuse keys -> no-op path
    configure_tracing()
    configure_tracing()  # must not raise on second call


def test_configure_tracing_disables_langfuse_when_keys_missing(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert configure_tracing(enable_langfuse=True).langfuse_enabled is False
