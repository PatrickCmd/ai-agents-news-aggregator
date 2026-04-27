from __future__ import annotations

import pytest


class _CapturingDigestRepo:
    def __init__(self, ids: list[int]) -> None:
        self._ids = ids
        self.calls = 0

    async def list_generated_today(self) -> list[int]:
        self.calls += 1
        return self._ids


@pytest.mark.asyncio
async def test_list_new_digests_returns_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_scheduler.handlers import list_new_digests

    repo = _CapturingDigestRepo([100, 101, 102])

    class _FakeSession:
        async def __aenter__(self) -> _FakeSession:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(list_new_digests, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(list_new_digests, "DigestRepository", lambda s: repo)

    out = await list_new_digests.run()
    assert out == {"digest_ids": [100, 101, 102]}
    assert repo.calls == 1


@pytest.mark.asyncio
async def test_list_new_digests_returns_empty_when_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scheduler.handlers import list_new_digests

    repo = _CapturingDigestRepo([])

    class _FakeSession:
        async def __aenter__(self) -> _FakeSession:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(list_new_digests, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(list_new_digests, "DigestRepository", lambda s: repo)

    out = await list_new_digests.run()
    assert out == {"digest_ids": []}
