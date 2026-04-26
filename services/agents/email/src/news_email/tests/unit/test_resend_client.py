from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_send_via_resend_returns_message_id() -> None:
    from news_email.resend_client import send_via_resend

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.resend.com"
        body = request.read()
        assert b'"to":["t@example.com"]' in body
        return httpx.Response(200, json={"id": "msg-1"})

    transport = httpx.MockTransport(handler)
    out = await send_via_resend(
        api_key="sk-1",  # pragma: allowlist secret
        sender_name="AI News",
        mail_from="hi@news.example",
        to="t@example.com",
        subject="hi",
        html="<p>hi</p>",
        transport=transport,
    )
    assert out["id"] == "msg-1"


@pytest.mark.asyncio
async def test_send_via_resend_passes_text_when_provided() -> None:
    from news_email.resend_client import send_via_resend

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b'"text":"plain version"' in body
        return httpx.Response(200, json={"id": "msg-2"})

    transport = httpx.MockTransport(handler)
    out = await send_via_resend(
        api_key="sk-1",  # pragma: allowlist secret
        sender_name="AI News",
        mail_from="hi@news.example",
        to="t@example.com",
        subject="hi",
        html="<p>hi</p>",
        text="plain version",
        transport=transport,
    )
    assert out["id"] == "msg-2"


@pytest.mark.asyncio
async def test_send_via_resend_includes_authorization_header() -> None:
    from news_email.resend_client import send_via_resend

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"id": "x"})

    transport = httpx.MockTransport(handler)
    await send_via_resend(
        api_key="sk-secret",  # pragma: allowlist secret
        sender_name="X",
        mail_from="x@x",
        to="t@example.com",
        subject="s",
        html="<p>h</p>",
        transport=transport,
    )
    assert captured["auth"] == "Bearer sk-secret"  # pragma: allowlist secret


@pytest.mark.asyncio
async def test_send_via_resend_raises_on_401() -> None:
    from news_email.resend_client import send_via_resend

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "auth"})

    transport = httpx.MockTransport(handler)
    with pytest.raises(RuntimeError, match="authentication"):
        await send_via_resend(
            api_key="bad",  # pragma: allowlist secret
            sender_name="x",
            mail_from="x@x",
            to="t@example.com",
            subject="s",
            html="<p>h</p>",
            transport=transport,
        )


@pytest.mark.asyncio
async def test_send_via_resend_raises_on_422() -> None:
    from news_email.resend_client import send_via_resend

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text="missing 'from' field")

    transport = httpx.MockTransport(handler)
    with pytest.raises(RuntimeError, match="validation"):
        await send_via_resend(
            api_key="sk",  # pragma: allowlist secret
            sender_name="x",
            mail_from="x@x",
            to="t@example.com",
            subject="s",
            html="<p>h</p>",
            transport=transport,
        )


@pytest.mark.asyncio
async def test_send_via_resend_raises_on_429() -> None:
    from news_email.resend_client import send_via_resend

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate"})

    transport = httpx.MockTransport(handler)
    with pytest.raises(RuntimeError, match="rate"):
        await send_via_resend(
            api_key="sk",  # pragma: allowlist secret
            sender_name="x",
            mail_from="x@x",
            to="t@example.com",
            subject="s",
            html="<p>h</p>",
            transport=transport,
        )


@pytest.mark.asyncio
async def test_send_via_resend_raises_on_500() -> None:
    """Other 4xx/5xx propagate via resp.raise_for_status()."""
    from news_email.resend_client import send_via_resend

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "server"})

    transport = httpx.MockTransport(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await send_via_resend(
            api_key="sk",  # pragma: allowlist secret
            sender_name="x",
            mail_from="x@x",
            to="t@example.com",
            subject="s",
            html="<p>h</p>",
            transport=transport,
        )
