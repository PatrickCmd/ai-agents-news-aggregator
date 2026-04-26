"""Async httpx wrapper around the Resend HTTP API.

Maps known error responses (401/422/429) to RuntimeError with explanatory
messages so the caller can pattern-match. Other 4xx/5xx propagate via
``resp.raise_for_status()`` (httpx.HTTPStatusError).
"""

from __future__ import annotations

from typing import Any

import httpx

RESEND_API_URL = "https://api.resend.com/emails"
RESEND_REQUEST_TIMEOUT = 10.0


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
        RuntimeError: on 401 (auth), 422 (validation), 429 (rate limit).
        httpx.HTTPStatusError: on other 4xx/5xx.
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
        raise RuntimeError("Resend authentication failed")
    if resp.status_code == 422:
        raise RuntimeError(f"Resend validation error: {resp.text}")
    if resp.status_code == 429:
        raise RuntimeError("Resend rate limit exceeded")
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    return data
