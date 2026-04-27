from __future__ import annotations

from uuid import UUID, uuid4

import pytest


class _CapturingUserRepo:
    def __init__(self, ids: list[UUID]) -> None:
        self._ids = ids
        self.calls = 0

    async def list_active_user_ids(self) -> list[UUID]:
        self.calls += 1
        return self._ids


@pytest.mark.asyncio
async def test_list_active_users_returns_uuid_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scheduler.handlers import list_active_users

    uids = [uuid4(), uuid4()]
    repo = _CapturingUserRepo(uids)

    class _FakeSession:
        async def __aenter__(self) -> _FakeSession:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(list_active_users, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(list_active_users, "UserRepository", lambda s: repo)

    out = await list_active_users.run()
    assert out == {"user_ids": [str(uid) for uid in uids]}
    assert repo.calls == 1


@pytest.mark.asyncio
async def test_list_active_users_returns_empty_when_no_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scheduler.handlers import list_active_users

    repo = _CapturingUserRepo([])

    class _FakeSession:
        async def __aenter__(self) -> _FakeSession:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(list_active_users, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(list_active_users, "UserRepository", lambda s: repo)

    out = await list_active_users.run()
    assert out == {"user_ids": []}
