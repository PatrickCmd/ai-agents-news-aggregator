"""Tenacity retry presets for network and LLM calls."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from news_observability.logging import get_logger

_log = get_logger("retry")

T = TypeVar("T")


class RetryableLLMError(Exception):
    """Wrap LLM-side errors that should be retried (rate limits, 5xx)."""


_TRANSIENT_EXCEPTIONS = (ConnectionError, TimeoutError, OSError)


def retry_transient(
    func: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    """Retry on network/transport errors (4 attempts, exponential backoff)."""

    async def wrapper(*args: object, **kwargs: object) -> T:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            retry=retry_if_exception_type(_TRANSIENT_EXCEPTIONS),
            reraise=True,
        ):
            with attempt:
                if attempt.retry_state.attempt_number > 1:
                    _log.warning("retry_transient attempt {}", attempt.retry_state.attempt_number)
                return await func(*args, **kwargs)
        raise RuntimeError("unreachable")  # pragma: no cover

    return wrapper


def retry_llm(
    func: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    """Retry on RetryableLLMError (5 attempts, slower backoff)."""

    async def wrapper(*args: object, **kwargs: object) -> T:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1.0, min=1, max=30),
            retry=retry_if_exception_type(RetryableLLMError),
            reraise=True,
        ):
            with attempt:
                if attempt.retry_state.attempt_number > 1:
                    _log.warning("retry_llm attempt {}", attempt.retry_state.attempt_number)
                return await func(*args, **kwargs)
        raise RuntimeError("unreachable")  # pragma: no cover

    return wrapper
