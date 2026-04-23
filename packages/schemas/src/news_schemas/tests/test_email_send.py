from datetime import datetime, timezone
from uuid import uuid4

from news_schemas.email_send import EmailSendIn, EmailSendOut, EmailSendStatus


def test_email_send_in_defaults():
    e = EmailSendIn(
        user_id=uuid4(),
        digest_id=1,
        to_address="a@b.com",
        subject="Your digest",
    )
    assert e.status == EmailSendStatus.PENDING
    assert e.provider == "resend"


def test_email_send_out_round_trip():
    now = datetime.now(timezone.utc)
    e = EmailSendOut(
        id=1,
        user_id=uuid4(),
        digest_id=1,
        provider="resend",
        to_address="a@b.com",
        subject="s",
        status=EmailSendStatus.SENT,
        provider_message_id="m",
        sent_at=now,
        error_message=None,
    )
    assert e.status == EmailSendStatus.SENT
