"""Async httpx wrapper around the Resend HTTP API.

Maps known error responses (401/422/429) to typed `ResendError` subclasses so
the pipeline can dispatch on exception type instead of substring-matching.
Other 4xx/5xx propagate via ``resp.raise_for_status()`` (httpx.HTTPStatusError).

**Retry policy lives at the call site, not here.** This client returns 4xx
mappings that should NOT be retried (auth/validation are deterministic
failures; rate-limit needs caller-side backoff). Retry policy lives at the
call site (the Lambda handler / CLI in `5.6`), not in the pipeline or this
client. The handler wraps `send_via_resend` with `retry_transient` from
`news_observability.retry`, which only retries on transport errors
(ConnectionError/TimeoutError/OSError) — those escape this function uncaught
via the `httpx.AsyncClient` context.
"""

from __future__ import annotations

from typing import Any

import httpx

RESEND_API_URL = "https://api.resend.com/emails"
RESEND_REQUEST_TIMEOUT = 10.0


class ResendError(RuntimeError):
    """Base class for Resend API errors mapped from 4xx responses."""


class ResendAuthError(ResendError):
    """Resend 401 — authentication failed (bad/missing API key)."""


class ResendValidationError(ResendError):
    """Resend 422 — request validation failed (e.g. unverified `from`)."""


class ResendRateLimitError(ResendError):
    """Resend 429 — rate limit exceeded (free tier: 100/day)."""


def _parse_validation_message(resp: httpx.Response) -> str:
    """Extract a clean message from a 422 response body.

    Avoids bloating logs / DB with the full JSON / rendered-HTML body and
    keeps any echoed request fields out of error strings.
    """
    try:
        body = resp.json()
    except ValueError:
        return "<non-json body>"
    if isinstance(body, dict):
        msg = body.get("message")
        if isinstance(msg, str) and msg:
            return msg
    return "<no message>"


async def send_via_resend(
    *,
    api_key: str,
    sender_name: str,
    mail_from: str,
    to: str,
    subject: str,
    html: str,
    text: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """POST to Resend; return parsed response JSON.

    Raises:
        ResendAuthError: on 401.
        ResendValidationError: on 422 (with parsed `message` field).
        ResendRateLimitError: on 429.
        httpx.HTTPStatusError: on other 4xx/5xx.
        httpx.ConnectError / httpx.ReadTimeout / etc: on transport failure
            (caller's `@retry_transient` should retry these).
    """
    payload: dict[str, Any] = {
        "from": f"{sender_name} <{mail_from}>",
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    async with httpx.AsyncClient(timeout=RESEND_REQUEST_TIMEOUT, transport=transport) as client:
        resp = await client.post(
            RESEND_API_URL,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
    if resp.status_code == 401:
        raise ResendAuthError("Resend authentication failed")
    if resp.status_code == 422:
        raise ResendValidationError(f"Resend validation error: {_parse_validation_message(resp)}")
    if resp.status_code == 429:
        raise ResendRateLimitError("Resend rate limit exceeded")
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    return data
