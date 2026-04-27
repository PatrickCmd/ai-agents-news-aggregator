"""User identity routes — GET /me, PUT /me/profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from news_db.repositories.user_repo import UserRepository
from news_observability.audit import AuditLogger
from news_schemas.audit import AgentName, DecisionType
from news_schemas.user_profile import UserOut, UserProfile
from sqlalchemy.ext.asyncio import AsyncSession

from news_api.deps import get_audit_logger, get_current_user, get_session_dep

router = APIRouter()


@router.get("/me", response_model=UserOut)
async def get_me(current_user: UserOut = Depends(get_current_user)) -> UserOut:  # noqa: B008
    return current_user


@router.put("/me/profile", response_model=UserOut)
async def put_my_profile(
    profile: UserProfile,
    current_user: UserOut = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session_dep),  # noqa: B008
    audit: AuditLogger = Depends(get_audit_logger),  # noqa: B008
) -> UserOut:
    repo = UserRepository(session)
    updated = await repo.update_profile(current_user.id, profile)
    first_completion = current_user.profile_completed_at is None
    if first_completion:
        updated = await repo.mark_profile_complete(current_user.id)
    await audit.log_decision(
        agent_name=AgentName.API,
        user_id=current_user.id,
        decision_type=DecisionType.PROFILE_UPDATE,
        input_text=profile.model_dump_json(),
        output_text="ok",
        metadata={"first_completion": first_completion},
    )
    return updated
