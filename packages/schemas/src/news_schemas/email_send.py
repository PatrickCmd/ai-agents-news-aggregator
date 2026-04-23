from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmailSendStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    BOUNCED = "bounced"


class EmailSendIn(BaseModel):
    user_id: UUID
    digest_id: int
    provider: str = "resend"
    to_address: EmailStr
    subject: str = Field(..., min_length=1)
    status: EmailSendStatus = EmailSendStatus.PENDING
    provider_message_id: str | None = None
    sent_at: datetime | None = None
    error_message: str | None = None


class EmailSendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: UUID
    digest_id: int
    provider: str
    to_address: EmailStr
    subject: str
    status: EmailSendStatus
    provider_message_id: str | None
    sent_at: datetime | None
    error_message: str | None
