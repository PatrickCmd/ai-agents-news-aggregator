from __future__ import annotations

from datetime import UTC, datetime

from news_schemas.email_send import EmailSendIn, EmailSendOut, EmailSendStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_db.models.email_send import EmailSend


class EmailSendRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, item: EmailSendIn) -> EmailSendOut:
        row = EmailSend(
            user_id=item.user_id,
            digest_id=item.digest_id,
            provider=item.provider,
            to_address=item.to_address,
            subject=item.subject,
            status=item.status.value,
            provider_message_id=item.provider_message_id,
            sent_at=item.sent_at,
            error_message=item.error_message,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return EmailSendOut.model_validate(row, from_attributes=True)

    async def mark_sent(self, email_send_id: int, provider_message_id: str) -> EmailSendOut:
        row = await self._session.get(EmailSend, email_send_id)
        if row is None:
            raise ValueError(f"email_send not found: {email_send_id}")
        row.status = EmailSendStatus.SENT.value
        row.provider_message_id = provider_message_id
        row.sent_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(row)
        return EmailSendOut.model_validate(row, from_attributes=True)

    async def mark_failed(self, email_send_id: int, error: str) -> EmailSendOut:
        row = await self._session.get(EmailSend, email_send_id)
        if row is None:
            raise ValueError(f"email_send not found: {email_send_id}")
        row.status = EmailSendStatus.FAILED.value
        row.error_message = error
        await self._session.commit()
        await self._session.refresh(row)
        return EmailSendOut.model_validate(row, from_attributes=True)

    async def get_sent_for_digest(self, digest_id: int) -> EmailSendOut | None:
        """Return the SENT row for *digest_id*, or None.

        Used by the Email agent's idempotency guard before any LLM/Resend call.
        """
        stmt = (
            select(EmailSend)
            .where(EmailSend.digest_id == digest_id)
            .where(EmailSend.status == EmailSendStatus.SENT.value)
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return EmailSendOut.model_validate(row, from_attributes=True) if row else None
