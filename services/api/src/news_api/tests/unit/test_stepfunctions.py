"""Unit tests for the start_remix boto3 wrapper."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from news_api.clients import stepfunctions as sfn_module


@pytest.fixture(autouse=True)
def _clear_client_cache():
    sfn_module._sfn_client.cache_clear()
    yield
    sfn_module._sfn_client.cache_clear()


async def test_start_remix_passes_payload_correctly(monkeypatch):
    fake_client = MagicMock()
    fake_client.start_execution.return_value = {
        "executionArn": "arn:aws:states:us-east-1:111:execution:news-remix-user-dev:abc",
        "startDate": datetime(2026, 4, 27, 10, 0, tzinfo=UTC),
    }
    monkeypatch.setattr(sfn_module, "_sfn_client", lambda: fake_client)

    user_id = uuid4()
    arn, started = await sfn_module.start_remix(
        state_machine_arn="arn:aws:states:us-east-1:111:stateMachine:news-remix-user-dev",
        user_id=user_id,
        lookback_hours=12,
    )
    assert arn.endswith(":abc")
    assert started.isoformat() == "2026-04-27T10:00:00+00:00"

    fake_client.start_execution.assert_called_once()
    call_kwargs = fake_client.start_execution.call_args.kwargs
    assert call_kwargs["stateMachineArn"].endswith(":news-remix-user-dev")
    payload = json.loads(call_kwargs["input"])
    assert payload == {"user_id": str(user_id), "lookback_hours": 12}
