"""Thin wrapper around boto3's Step Functions client for start_remix.

Single source of truth for `import boto3` in the API service.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from functools import lru_cache
from uuid import UUID

import boto3


@lru_cache(maxsize=1)
def _sfn_client():
    """One client per warm container — same lifetime as runtime credentials."""
    return boto3.client("stepfunctions")


async def start_remix(
    *,
    state_machine_arn: str,
    user_id: UUID,
    lookback_hours: int,
) -> tuple[str, datetime]:
    """Trigger news-remix-user with `{user_id, lookback_hours}` input.

    Returns (executionArn, startDate). boto3 is sync, so we offload to a
    worker thread to avoid blocking the asyncio event loop.
    """
    payload = json.dumps(
        {
            "user_id": str(user_id),
            "lookback_hours": lookback_hours,
        }
    )
    resp = await asyncio.to_thread(
        _sfn_client().start_execution,
        stateMachineArn=state_machine_arn,
        input=payload,
    )
    return resp["executionArn"], resp["startDate"]
