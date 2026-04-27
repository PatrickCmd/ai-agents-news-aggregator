"""POST /v1/remix — trigger news-remix-user state machine."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from news_observability.audit import AuditLogger
from news_schemas.audit import AgentName, DecisionType
from news_schemas.user_profile import UserOut
from pydantic import BaseModel, Field

from news_api.clients.stepfunctions import start_remix
from news_api.deps import get_audit_logger, get_current_user
from news_api.settings import get_api_settings

router = APIRouter()


class RemixRequest(BaseModel):
    lookback_hours: int = Field(default=24, ge=1, le=168)


class RemixResponse(BaseModel):
    execution_arn: str
    started_at: datetime


@router.post("/remix", response_model=RemixResponse, status_code=status.HTTP_202_ACCEPTED)
async def post_remix(
    body: RemixRequest,
    current_user: UserOut = Depends(get_current_user),  # noqa: B008
    audit: AuditLogger = Depends(get_audit_logger),  # noqa: B008
) -> RemixResponse:
    if current_user.profile_completed_at is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"error": "profile_incomplete"},
        )

    settings = get_api_settings()
    arn, started = await start_remix(
        state_machine_arn=settings.remix_state_machine_arn,
        user_id=current_user.id,
        lookback_hours=body.lookback_hours,
    )
    await audit.log_decision(
        agent_name=AgentName.API,
        user_id=current_user.id,
        decision_type=DecisionType.REMIX_TRIGGERED,
        input_text=f"lookback_hours={body.lookback_hours}",
        output_text=arn,
        metadata={"execution_arn": arn, "lookback_hours": body.lookback_hours},
    )
    return RemixResponse(execution_arn=arn, started_at=started)
