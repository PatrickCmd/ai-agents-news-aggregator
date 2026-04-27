from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentName(StrEnum):
    DIGEST = "digest_agent"
    EDITOR = "editor_agent"
    EMAIL = "email_agent"
    WEB_SEARCH = "web_search_agent"
    API = "api"


class DecisionType(StrEnum):
    SUMMARY = "summary"
    RANK = "rank"
    INTRO = "intro"
    SEARCH_RESULT = "search_result"
    PROFILE_UPDATE = "profile_update"
    REMIX_TRIGGERED = "remix_triggered"


class AuditLogIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: AgentName
    user_id: UUID | None = None
    decision_type: DecisionType
    input_summary: str
    output_summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)
