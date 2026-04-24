import pytest

from news_observability.retry import RetryableLLMError, retry_llm, retry_transient


@pytest.mark.asyncio
async def test_retry_transient_retries_then_succeeds():
    calls = {"n": 0}

    @retry_transient
    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    assert await flaky() == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_llm_retries_on_retryable_error():
    calls = {"n": 0}

    @retry_llm
    async def llm_call() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise RetryableLLMError("rate limited")
        return "ok"

    assert await llm_call() == "ok"


@pytest.mark.asyncio
async def test_retry_llm_does_not_retry_on_plain_exception():
    @retry_llm
    async def bad() -> str:
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        await bad()
