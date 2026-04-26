# Agents (Sub-project #2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship three independent AWS Lambda agents (Digest, Editor, Email) using the OpenAI Agents SDK with default backend selection, packaged as zip artifacts in S3, plus per-agent Terraform modules and a shared artifacts bucket added to `infra/bootstrap/`.

**Architecture:** Each agent is a standalone uv workspace package under `services/agents/<name>/` containing a Pydantic-typed agent, a deterministic pipeline, a Typer CLI for local dev, and a `lambda_handler.py` for AWS. Each agent has its own Terraform module under `infra/<name>/` that consumes a shared `lambda_artifacts` S3 bucket created by `infra/bootstrap/`. LLM-side schemas live in `news_schemas/agent_io.py`; new repo methods live in existing `packages/db` repositories. Composition (Email LLM produces intro/subject; Resend send is deterministic Python) gives us testable, debuggable agents.

**Tech Stack:** Python 3.12, OpenAI Agents SDK (`openai-agents`) — model passed as a plain string, SDK picks the backend (default: Responses API) — Pydantic v2, SQLAlchemy async, Jinja2 (email templates), httpx (Resend HTTP API), AWS Lambda + SSM SecureString, Terraform 6.42.0, testcontainers-postgres for integration tests, pytest + pytest-asyncio.

**Spec:** [docs/superpowers/specs/2026-04-25-agents-design.md](../specs/2026-04-25-agents-design.md)

**Branch:** `sub-project#2`

---

## Phase 0 — Reading + setup

- [ ] **Step 0.1: Read the spec and confirm branch state**

```bash
git status
git branch --show-current        # expected: sub-project#2
git log --oneline -5             # confirm spec commit 088f9ae is HEAD or close
cat docs/superpowers/specs/2026-04-25-agents-design.md | head -50
```

- [ ] **Step 0.2: Verify baseline is green before starting**

```bash
uv run pytest -q
uv run mypy packages
uv run ruff check
```

Expected: all green. If anything fails, STOP and ask the user — do not start sub-project #2 work on a broken main.

---

## Phase 1 — Schemas + repository methods

This phase ships the contracts and persistence primitives the three agents need. No Lambda code, no agent code yet — just the shared layer. Test-driven throughout.

### Task 1.1: Create `agent_io.py` schemas

**Files:**
- Create: [packages/schemas/src/news_schemas/agent_io.py](packages/schemas/src/news_schemas/agent_io.py)
- Create: [packages/schemas/src/news_schemas/tests/test_agent_io.py](packages/schemas/src/news_schemas/tests/test_agent_io.py)

- [ ] **Step 1.1.1: Write the failing tests**

```python
# packages/schemas/src/news_schemas/tests/test_agent_io.py
from __future__ import annotations

import pytest
from pydantic import ValidationError

from news_schemas.agent_io import (
    ArticleRanking,
    DigestSummary,
    EditorDecision,
    EmailIntroduction,
)


def test_digest_summary_valid() -> None:
    s = DigestSummary(
        summary="A " + ("very useful summary " * 5),
        key_takeaways=["t1", "t2"],
    )
    assert s.summary.startswith("A ")
    assert len(s.key_takeaways) == 2


def test_digest_summary_rejects_short_summary() -> None:
    with pytest.raises(ValidationError):
        DigestSummary(summary="short", key_takeaways=[])


def test_digest_summary_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        DigestSummary.model_validate(
            {
                "summary": "x" * 60,
                "key_takeaways": [],
                "unexpected": "nope",
            }
        )


def test_article_ranking_score_bounds() -> None:
    ArticleRanking(
        article_id=1, score=0, why_ranked="ten chars long", key_topics=[]
    )
    ArticleRanking(
        article_id=1, score=100, why_ranked="ten chars long", key_topics=[]
    )
    with pytest.raises(ValidationError):
        ArticleRanking(
            article_id=1, score=101, why_ranked="ten chars long", key_topics=[]
        )


def test_editor_decision_valid() -> None:
    d = EditorDecision(
        rankings=[
            ArticleRanking(
                article_id=1, score=80, why_ranked="ten chars long", key_topics=["x"]
            )
        ],
        top_themes=["theme"],
        overall_summary="all good",
    )
    assert len(d.rankings) == 1


def test_email_introduction_valid() -> None:
    e = EmailIntroduction(
        greeting="Hi Pat,",
        introduction="Welcome to today's digest. Lots happening in agents land.",
        highlight="The biggest story is the new Agents SDK release.",
        subject_line="AI Daily — agents go GA",
    )
    assert e.subject_line.startswith("AI Daily")
```

- [ ] **Step 1.1.2: Run tests to confirm they fail with ImportError**

```bash
uv run pytest packages/schemas/src/news_schemas/tests/test_agent_io.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'news_schemas.agent_io'`.

- [ ] **Step 1.1.3: Implement the schemas**

```python
# packages/schemas/src/news_schemas/agent_io.py
"""LLM-side I/O schemas for the three agents.

LLM-side: every field is a primitive (str/int/list[str]/list[BaseModel]).
No HttpUrl, no EmailStr — OpenAI structured outputs reject those (per memory `openai_structured_outputs_format`).
URLs/emails are joined back from the DB after the LLM returns.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DigestSummary(BaseModel):
    """Output of the Digest agent for a single article."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(..., min_length=50, max_length=500)
    key_takeaways: list[str] = Field(default_factory=list, max_length=5)


class ArticleRanking(BaseModel):
    """One ranked article from the Editor agent."""

    model_config = ConfigDict(extra="forbid")

    article_id: int
    score: int = Field(..., ge=0, le=100)
    why_ranked: str = Field(..., min_length=10, max_length=300)
    key_topics: list[str] = Field(default_factory=list, max_length=5)


class EditorDecision(BaseModel):
    """Full output of the Editor agent for a user."""

    model_config = ConfigDict(extra="forbid")

    rankings: list[ArticleRanking] = Field(..., max_length=100)
    top_themes: list[str] = Field(default_factory=list, max_length=10)
    overall_summary: str = Field(default="", max_length=600)


class EmailIntroduction(BaseModel):
    """Output of the Email agent — the personalised intro + subject."""

    model_config = ConfigDict(extra="forbid")

    greeting: str = Field(..., min_length=5, max_length=100)
    introduction: str = Field(..., min_length=20, max_length=600)
    highlight: str = Field(..., min_length=10, max_length=300)
    subject_line: str = Field(..., min_length=5, max_length=120)
```

- [ ] **Step 1.1.4: Run the tests; verify they pass**

```bash
uv run pytest packages/schemas/src/news_schemas/tests/test_agent_io.py -v
uv run mypy packages/schemas
uv run ruff check packages/schemas
```

Expected: all green.

- [ ] **Step 1.1.5: Commit**

```bash
git add packages/schemas/src/news_schemas/agent_io.py packages/schemas/src/news_schemas/tests/test_agent_io.py
git commit -m "feat(schemas): add agent_io with DigestSummary/EditorDecision/EmailIntroduction"
```

---

### Task 1.2: `ArticleRepository.update_summary`

**Files:**
- Modify: [packages/db/src/news_db/repositories/article_repo.py](packages/db/src/news_db/repositories/article_repo.py)
- Modify: [packages/db/src/news_db/tests/test_article_repo.py](packages/db/src/news_db/tests/test_article_repo.py)

- [ ] **Step 1.2.1: Write the failing test**

Add to `packages/db/src/news_db/tests/test_article_repo.py` (create the file if it doesn't already exist; otherwise append). If the project already exercises the article repo via integration tests under `tests/integration/`, add the test there in `tests/integration/test_article_repo_summary.py`:

```python
# tests/integration/test_article_repo_summary.py
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from news_db.repositories.article_repo import ArticleRepository
from news_schemas.article import ArticleIn, SourceType
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_update_summary_persists(session: AsyncSession) -> None:
    repo = ArticleRepository(session)
    await repo.upsert_many(
        [
            ArticleIn(
                source_type=SourceType.RSS,
                source_name="t",
                external_id="ext-1",
                title="t",
                url="https://example.com/1",
                published_at=datetime.now(UTC),
            )
        ]
    )
    fetched = await repo.get_recent(hours=1)
    assert fetched and fetched[0].summary is None

    await repo.update_summary(fetched[0].id, "a useful summary " * 5)
    again = await repo.get_by_id(fetched[0].id)
    assert again is not None
    assert again.summary is not None
    assert "useful summary" in again.summary
```

- [ ] **Step 1.2.2: Run test, expect failure**

```bash
uv run pytest tests/integration/test_article_repo_summary.py -v
```

Expected: FAIL with `AttributeError: 'ArticleRepository' object has no attribute 'update_summary'`.

- [ ] **Step 1.2.3: Implement `update_summary`**

Add to `packages/db/src/news_db/repositories/article_repo.py`:

```python
    async def update_summary(self, article_id: int, summary: str) -> None:
        row = await self._session.get(Article, article_id)
        if row is None:
            raise ValueError(f"article not found: {article_id}")
        row.summary = summary
        await self._session.commit()
```

- [ ] **Step 1.2.4: Run test, expect pass**

```bash
uv run pytest tests/integration/test_article_repo_summary.py -v
```

Expected: PASS.

- [ ] **Step 1.2.5: Commit**

```bash
git add packages/db/src/news_db/repositories/article_repo.py tests/integration/test_article_repo_summary.py
git commit -m "feat(db): ArticleRepository.update_summary"
```

---

### Task 1.3: `ArticleRepository.get_unsummarized` + `get_recent_with_summaries`

**Files:**
- Modify: [packages/db/src/news_db/repositories/article_repo.py](packages/db/src/news_db/repositories/article_repo.py)
- Create: [tests/integration/test_article_repo_summary_queries.py](tests/integration/test_article_repo_summary_queries.py)

- [ ] **Step 1.3.1: Write the failing tests**

```python
# tests/integration/test_article_repo_summary_queries.py
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from news_db.repositories.article_repo import ArticleRepository
from news_schemas.article import ArticleIn, SourceType
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed(session: AsyncSession) -> ArticleRepository:
    repo = ArticleRepository(session)
    now = datetime.now(UTC)
    await repo.upsert_many(
        [
            ArticleIn(
                source_type=SourceType.RSS,
                source_name="t",
                external_id=f"ext-{i}",
                title=f"t{i}",
                url=f"https://example.com/{i}",
                content_text=f"content {i}",
                published_at=now,
            )
            for i in range(3)
        ]
    )
    return repo


@pytest.mark.asyncio
async def test_get_unsummarized_returns_only_null_summary(session: AsyncSession) -> None:
    repo = await _seed(session)
    rows = await repo.get_recent(hours=1)
    await repo.update_summary(rows[0].id, "summary " * 10)

    pending = await repo.get_unsummarized(hours=1, limit=10)
    pending_ids = {r.id for r in pending}
    assert rows[0].id not in pending_ids
    assert {rows[1].id, rows[2].id} <= pending_ids


@pytest.mark.asyncio
async def test_get_recent_with_summaries_filters_null(session: AsyncSession) -> None:
    repo = await _seed(session)
    rows = await repo.get_recent(hours=1)
    await repo.update_summary(rows[0].id, "summary " * 10)
    await repo.update_summary(rows[1].id, "another summary " * 5)

    summarized = await repo.get_recent_with_summaries(hours=1, limit=10)
    summarized_ids = {r.id for r in summarized}
    assert rows[0].id in summarized_ids
    assert rows[1].id in summarized_ids
    assert rows[2].id not in summarized_ids


@pytest.mark.asyncio
async def test_get_recent_with_summaries_respects_limit(session: AsyncSession) -> None:
    repo = await _seed(session)
    rows = await repo.get_recent(hours=1)
    for r in rows:
        await repo.update_summary(r.id, "x" * 60)
    summarized = await repo.get_recent_with_summaries(hours=1, limit=2)
    assert len(summarized) == 2
```

- [ ] **Step 1.3.2: Run, expect failures**

```bash
uv run pytest tests/integration/test_article_repo_summary_queries.py -v
```

Expected: FAIL — methods missing.

- [ ] **Step 1.3.3: Implement the methods**

Add to `article_repo.py` (above `get_existing_external_ids`):

```python
    async def get_unsummarized(self, hours: int, limit: int = 50) -> list[ArticleOut]:
        """Articles published within *hours* whose `summary IS NULL`.

        Used by the Digest agent's local CLI sweep mode and by #3's fan-out.
        """
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        stmt = (
            select(Article)
            .where(Article.published_at >= cutoff)
            .where(Article.summary.is_(None))
            .order_by(Article.published_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [ArticleOut.model_validate(r, from_attributes=True) for r in rows]

    async def get_recent_with_summaries(
        self, hours: int, limit: int = 100
    ) -> list[ArticleOut]:
        """Recent articles where `summary IS NOT NULL`. Editor's candidate pool."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        stmt = (
            select(Article)
            .where(Article.published_at >= cutoff)
            .where(Article.summary.is_not(None))
            .order_by(Article.published_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [ArticleOut.model_validate(r, from_attributes=True) for r in rows]
```

- [ ] **Step 1.3.4: Run, expect pass**

```bash
uv run pytest tests/integration/test_article_repo_summary_queries.py -v
uv run mypy packages/db
```

- [ ] **Step 1.3.5: Commit**

```bash
git add packages/db/src/news_db/repositories/article_repo.py tests/integration/test_article_repo_summary_queries.py
git commit -m "feat(db): ArticleRepository.get_unsummarized + get_recent_with_summaries"
```

---

### Task 1.4: `EmailSendRepository.get_sent_for_digest`

**Files:**
- Modify: [packages/db/src/news_db/repositories/email_send_repo.py](packages/db/src/news_db/repositories/email_send_repo.py)
- Create: [tests/integration/test_email_send_repo_idempotency.py](tests/integration/test_email_send_repo_idempotency.py)

- [ ] **Step 1.4.1: Write the failing test**

```python
# tests/integration/test_email_send_repo_idempotency.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from news_db.repositories.digest_repo import DigestRepository
from news_db.repositories.email_send_repo import EmailSendRepository
from news_db.repositories.user_repo import UserRepository
from news_schemas.digest import DigestIn, DigestStatus
from news_schemas.email_send import EmailSendIn
from news_schemas.user_profile import (
    Interests,
    Preferences,
    ReadingTime,
    UserIn,
    UserProfile,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _profile() -> UserProfile:
    return UserProfile(
        background=["dev"],
        interests=Interests(primary=["AI"]),
        preferences=Preferences(),
        goals=[],
        reading_time=ReadingTime(daily_limit="20m", preferred_article_count="5"),
    )


@pytest.mark.asyncio
async def test_get_sent_for_digest_returns_none_when_missing(
    session: AsyncSession,
) -> None:
    repo = EmailSendRepository(session)
    assert await repo.get_sent_for_digest(999_999) is None


@pytest.mark.asyncio
async def test_get_sent_for_digest_returns_sent_row(session: AsyncSession) -> None:
    user = await UserRepository(session).upsert_by_clerk_id(
        UserIn(
            clerk_user_id=f"clerk-{uuid4()}",
            email="t@example.com",
            name="T",
            email_name="T",
            profile=_profile(),
        )
    )
    digest = await DigestRepository(session).create(
        DigestIn(
            user_id=user.id,
            period_start=datetime.now(UTC) - timedelta(hours=24),
            period_end=datetime.now(UTC),
            ranked_articles=[],
            article_count=0,
            status=DigestStatus.GENERATED,
        )
    )

    email_repo = EmailSendRepository(session)
    pending = await email_repo.create(
        EmailSendIn(
            user_id=user.id,
            digest_id=digest.id,
            to_address="t@example.com",
            subject="hi",
        )
    )
    # Pending should not count as "sent"
    assert await email_repo.get_sent_for_digest(digest.id) is None
    await email_repo.mark_sent(pending.id, provider_message_id="msg-1")
    found = await email_repo.get_sent_for_digest(digest.id)
    assert found is not None
    assert found.provider_message_id == "msg-1"
```

- [ ] **Step 1.4.2: Run, expect failure**

```bash
uv run pytest tests/integration/test_email_send_repo_idempotency.py -v
```

Expected: FAIL — `AttributeError: ... has no attribute 'get_sent_for_digest'`.

- [ ] **Step 1.4.3: Implement the method**

Add to `email_send_repo.py`:

```python
    async def get_sent_for_digest(self, digest_id: int) -> EmailSendOut | None:
        """Return the SENT row for *digest_id*, or None.

        Used by the Email agent's idempotency guard before any LLM/Resend call.
        """
        from sqlalchemy import select

        stmt = (
            select(EmailSend)
            .where(EmailSend.digest_id == digest_id)
            .where(EmailSend.status == EmailSendStatus.SENT.value)
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return EmailSendOut.model_validate(row, from_attributes=True) if row else None
```

(Move the `from sqlalchemy import select` to the top of the file with the other imports.)

- [ ] **Step 1.4.4: Run, expect pass**

```bash
uv run pytest tests/integration/test_email_send_repo_idempotency.py -v
uv run mypy packages/db
```

- [ ] **Step 1.4.5: Commit**

```bash
git add packages/db/src/news_db/repositories/email_send_repo.py tests/integration/test_email_send_repo_idempotency.py
git commit -m "feat(db): EmailSendRepository.get_sent_for_digest idempotency lookup"
```

---

### Task 1.5: Add `MailSettings` to `news_config`

**Files:**
- Modify: [packages/config/src/news_config/settings.py](packages/config/src/news_config/settings.py)
- Create: [packages/config/src/news_config/tests/test_mail_settings.py](packages/config/src/news_config/tests/test_mail_settings.py)

- [ ] **Step 1.5.1: Write the failing test**

```python
# packages/config/src/news_config/tests/test_mail_settings.py
from __future__ import annotations

import pytest

from news_config.settings import MailSettings


def test_mail_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_FROM", "noreply@news.example.com")
    monkeypatch.setenv("SENDER_NAME", "AI News Digest")
    monkeypatch.setenv("MAIL_TO_DEFAULT", "p@example.com")
    s = MailSettings()
    assert s.mail_from == "noreply@news.example.com"
    assert s.sender_name == "AI News Digest"
    assert s.mail_to_default == "p@example.com"


def test_mail_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAIL_FROM", raising=False)
    monkeypatch.delenv("SENDER_NAME", raising=False)
    monkeypatch.delenv("MAIL_TO_DEFAULT", raising=False)
    s = MailSettings()
    assert s.mail_from == ""
    assert s.sender_name == "AI News Digest"
    assert s.mail_to_default == ""
```

- [ ] **Step 1.5.2: Run, expect failure**

```bash
uv run pytest packages/config/src/news_config/tests/test_mail_settings.py -v
```

Expected: FAIL — `ImportError: cannot import name 'MailSettings'`.

- [ ] **Step 1.5.3: Implement `MailSettings`**

Append to `packages/config/src/news_config/settings.py`:

```python
class MailSettings(_Base):
    mail_from: str = Field(default="", alias="MAIL_FROM")
    sender_name: str = Field(default="AI News Digest", alias="SENDER_NAME")
    mail_to_default: str = Field(default="", alias="MAIL_TO_DEFAULT")
```

- [ ] **Step 1.5.4: Run, expect pass**

```bash
uv run pytest packages/config/src/news_config/tests/test_mail_settings.py -v
```

- [ ] **Step 1.5.5: Commit**

```bash
git add packages/config/src/news_config/settings.py packages/config/src/news_config/tests/test_mail_settings.py
git commit -m "feat(config): MailSettings (mail_from / sender_name / mail_to_default)"
```

---

### Task 1.6: Phase 1 verification

- [ ] **Step 1.6.1: Run the full check**

```bash
uv run ruff check
uv run ruff format --check
uv run mypy packages
uv run pytest -q
```

All green. Phase 1 done.

---

## Phase 2 — Bootstrap extension (artifacts S3 bucket)

This is a one-time Terraform change so the per-agent modules later can reference `data.terraform_remote_state.bootstrap.outputs.lambda_artifacts_bucket`.

### Task 2.1: Extend `infra/bootstrap/`

**Files:**
- Modify: [infra/bootstrap/main.tf](infra/bootstrap/main.tf)
- Modify: [infra/bootstrap/outputs.tf](infra/bootstrap/outputs.tf)

- [ ] **Step 2.1.1: Add the bucket resources to `main.tf`**

Append to `infra/bootstrap/main.tf`:

```hcl
# Lambda artifact bucket — holds per-agent zip artifacts for #2.

resource "aws_s3_bucket" "lambda_artifacts" {
  bucket = "news-aggregator-lambda-artifacts-${data.aws_caller_identity.current.account_id}"

  tags = {
    Project = "news-aggregator"
    Purpose = "lambda-artifacts"
  }
}

resource "aws_s3_bucket_versioning" "lambda_artifacts" {
  bucket = aws_s3_bucket.lambda_artifacts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lambda_artifacts" {
  bucket = aws_s3_bucket.lambda_artifacts.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "lambda_artifacts" {
  bucket                  = aws_s3_bucket.lambda_artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "lambda_artifacts" {
  bucket = aws_s3_bucket.lambda_artifacts.id

  rule {
    id     = "expire-old-artifacts"
    status = "Enabled"
    noncurrent_version_expiration { noncurrent_days = 90 }
  }
}
```

- [ ] **Step 2.1.2: Add the output**

Append to `infra/bootstrap/outputs.tf`:

```hcl
output "lambda_artifacts_bucket" {
  description = "S3 bucket holding per-agent Lambda zip artifacts"
  value       = aws_s3_bucket.lambda_artifacts.bucket
}
```

- [ ] **Step 2.1.3: Plan + apply bootstrap**

```bash
cd infra/bootstrap
terraform plan
```

Expected plan: 5 resources to add (bucket + versioning + sse + public-access-block + lifecycle).

```bash
terraform apply
```

- [ ] **Step 2.1.4: Verify the new output is set**

```bash
terraform output lambda_artifacts_bucket
```

Expected: `news-aggregator-lambda-artifacts-<your-account-id>`. Save this — agent Terraform modules will read it via remote state.

```bash
cd ../..
```

- [ ] **Step 2.1.5: Commit**

```bash
git add infra/bootstrap/main.tf infra/bootstrap/outputs.tf
git commit -m "infra(bootstrap): add lambda_artifacts S3 bucket for sub-project #2"
```

---

## Phase 3 — Digest agent

The Digest agent is the smallest and best place to validate the entire pattern (workspace package, settings, agent, pipeline, CLI, Lambda handler, package_docker.py, deploy.py). Editor and Email reuse the same shape.

### Task 3.1: Create `services/agents/digest/` workspace package

**Files:**
- Create: [services/agents/digest/pyproject.toml](services/agents/digest/pyproject.toml)
- Create: [services/agents/digest/src/news_digest/__init__.py](services/agents/digest/src/news_digest/__init__.py)
- Modify: [pyproject.toml](pyproject.toml) (root) — add new workspace members + sources
- Modify: [mypy.ini](mypy.ini) (extend `mypy_path` if it exists)

- [ ] **Step 3.1.1: Create the agent's pyproject.toml**

```toml
# services/agents/digest/pyproject.toml
[project]
name = "news_digest"
version = "0.1.0"
requires-python = ">=3.12"
description = "Digest agent — per-article LLM summarisation Lambda"
dependencies = [
    "openai-agents>=0.14.5",
    "pydantic>=2.13.3",
    "pydantic-settings>=2.5",
    "loguru>=0.7.3",
    "typer>=0.24.2",
    "boto3>=1.42.95",
    "news_schemas",
    "news_config",
    "news_observability",
    "news_db",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/news_digest"]
```

- [ ] **Step 3.1.2: Create the package init**

```python
# services/agents/digest/src/news_digest/__init__.py
"""Digest agent — per-article LLM summarisation."""
```

- [ ] **Step 3.1.3: Add to root workspace**

Edit `pyproject.toml` (root):

```toml
[tool.uv.workspace]
members = [
    "packages/schemas",
    "packages/config",
    "packages/observability",
    "packages/db",
    "services/scraper",
    "services/agents/digest",
]

[tool.uv.sources]
news_schemas = { workspace = true }
news_config = { workspace = true }
news_observability = { workspace = true }
news_db = { workspace = true }
news_scraper = { workspace = true }
news_digest = { workspace = true }
```

- [ ] **Step 3.1.4: Sync the workspace**

```bash
uv sync --all-packages
```

Expected: Resolves and installs `news_digest` editable.

- [ ] **Step 3.1.5: Commit (no tests yet — package skeleton only)**

```bash
git add services/agents/digest/pyproject.toml services/agents/digest/src/news_digest/__init__.py pyproject.toml uv.lock
git commit -m "feat(digest): scaffold news_digest workspace package"
```

---

### Task 3.2: `news_digest.settings`

**Files:**
- Create: [services/agents/digest/src/news_digest/settings.py](services/agents/digest/src/news_digest/settings.py)
- Create: [services/agents/digest/src/news_digest/tests/__init__.py](services/agents/digest/src/news_digest/tests/__init__.py)
- Create: [services/agents/digest/src/news_digest/tests/unit/__init__.py](services/agents/digest/src/news_digest/tests/unit/__init__.py)
- Create: [services/agents/digest/src/news_digest/tests/unit/test_settings.py](services/agents/digest/src/news_digest/tests/unit/test_settings.py)

- [ ] **Step 3.2.1: Write the failing test**

```python
# services/agents/digest/src/news_digest/tests/unit/test_settings.py
from __future__ import annotations

import pytest


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGEST_MAX_CONTENT_CHARS", raising=False)
    from news_digest.settings import DigestSettings

    s = DigestSettings()
    assert s.max_content_chars == 8000


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGEST_MAX_CONTENT_CHARS", "1500")
    from news_digest.settings import DigestSettings

    s = DigestSettings()
    assert s.max_content_chars == 1500
```

- [ ] **Step 3.2.2: Run, expect failure**

```bash
uv run pytest services/agents/digest/src/news_digest/tests -v
```

Expected: FAIL — module not found.

- [ ] **Step 3.2.3: Implement `settings.py`**

```python
# services/agents/digest/src/news_digest/settings.py
"""Digest-agent-specific settings, layered on top of news_config."""

from __future__ import annotations

from news_config.settings import OpenAISettings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DigestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    max_content_chars: int = Field(default=8000, alias="DIGEST_MAX_CONTENT_CHARS")
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
```

- [ ] **Step 3.2.4: Run, expect pass**

```bash
uv run pytest services/agents/digest/src/news_digest/tests -v
uv run mypy services/agents/digest
```

- [ ] **Step 3.2.5: Commit**

```bash
git add services/agents/digest
git commit -m "feat(digest): DigestSettings (max_content_chars + openai)"
```

---

### Task 3.3: `news_digest.agent` — `build_agent` factory

**Files:**
- Create: [services/agents/digest/src/news_digest/agent.py](services/agents/digest/src/news_digest/agent.py)
- Create: [services/agents/digest/src/news_digest/tests/unit/test_agent.py](services/agents/digest/src/news_digest/tests/unit/test_agent.py)

- [ ] **Step 3.3.1: Write the failing test**

```python
# services/agents/digest/src/news_digest/tests/unit/test_agent.py
from __future__ import annotations

import pytest


def test_build_agent_returns_agent_with_digest_summary_output_type() -> None:
    from news_digest.agent import build_agent
    from news_schemas.agent_io import DigestSummary

    agent = build_agent(model="gpt-5.4-mini")
    assert agent.output_type is DigestSummary
    assert agent.name == "DigestAgent"


def test_build_agent_passes_model_string_through() -> None:
    """Pass the model as a string — let the SDK pick the backend (default: Responses API)."""
    from news_digest.agent import build_agent

    agent = build_agent(model="gpt-5.4-mini")
    assert agent.model == "gpt-5.4-mini"
```

- [ ] **Step 3.3.2: Run, expect failure**

```bash
uv run pytest services/agents/digest/src/news_digest/tests/unit/test_agent.py -v
```

- [ ] **Step 3.3.3: Implement `agent.py`**

```python
# services/agents/digest/src/news_digest/agent.py
"""Digest agent — per-article LLM summariser.

The model is passed as a string; the OpenAI Agents SDK selects the backend
(default: Responses API) — no manual `OpenAIChatCompletionsModel` wrapping.
"""

from __future__ import annotations

from agents import Agent
from news_schemas.agent_io import DigestSummary


_INSTRUCTIONS = (
    "You are an expert AI news analyst and summariser. Your role is to create "
    "concise, engaging digest summaries of AI-related content (YouTube videos, "
    "blog posts, articles).\n\n"
    "Your task:\n"
    "1. Write a 2-3 sentence summary (50-500 chars) highlighting the key points, "
    "why it's significant, and practical impact.\n"
    "2. List 0-5 key takeaways, one short phrase each.\n\n"
    "Focus on technical accuracy, key insights, and actionable takeaways. Avoid "
    "marketing fluff or hype."
)


def build_agent(*, model: str) -> Agent[DigestSummary]:
    return Agent(
        name="DigestAgent",
        instructions=_INSTRUCTIONS,
        model=model,
        output_type=DigestSummary,
    )


def build_user_prompt(
    *,
    title: str,
    url: str,
    source_type: str,
    source_name: str,
    content: str,
    max_chars: int,
) -> str:
    truncated = content[:max_chars] if content else ""
    return (
        f"Article source: {source_type} — {source_name}\n"
        f"Original title: {title}\n"
        f"URL: {url}\n\n"
        f"CONTENT:\n{truncated}"
    )
```

- [ ] **Step 3.3.4: Run, expect pass**

```bash
uv run pytest services/agents/digest/src/news_digest/tests/unit/test_agent.py -v
```

- [ ] **Step 3.3.5: Commit**

```bash
git add services/agents/digest/src/news_digest/agent.py services/agents/digest/src/news_digest/tests/unit/test_agent.py
git commit -m "feat(digest): build_agent + build_user_prompt"
```

---

### Task 3.4: `news_digest.pipeline` — `summarize_article`

**Files:**
- Create: [services/agents/digest/src/news_digest/pipeline.py](services/agents/digest/src/news_digest/pipeline.py)
- Create: [services/agents/digest/src/news_digest/tests/unit/test_pipeline.py](services/agents/digest/src/news_digest/tests/unit/test_pipeline.py)

- [ ] **Step 3.4.1: Write the failing tests**

```python
# services/agents/digest/src/news_digest/tests/unit/test_pipeline.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from news_schemas.agent_io import DigestSummary
from news_schemas.article import ArticleOut, SourceType
from news_schemas.audit import AuditLogIn


@dataclass
class _Usage:
    input_tokens: int = 100
    output_tokens: int = 50
    total_tokens: int = 150
    requests: int = 1


@dataclass
class _Wrapper:
    usage: _Usage


@dataclass
class _FakeResult:
    final_output: DigestSummary
    context_wrapper: _Wrapper


class _CapturingArticleRepo:
    def __init__(self, article: ArticleOut | None) -> None:
        self._article = article
        self.updates: list[tuple[int, str]] = []

    async def get_by_id(self, article_id: int) -> ArticleOut | None:
        return self._article

    async def update_summary(self, article_id: int, summary: str) -> None:
        self.updates.append((article_id, summary))


class _CapturingAuditRepo:
    def __init__(self) -> None:
        self.entries: list[AuditLogIn] = []

    async def insert(self, entry: AuditLogIn) -> None:
        self.entries.append(entry)


def _article(*, summary: str | None, content_text: str | None = "x" * 200) -> ArticleOut:
    return ArticleOut(
        id=42,
        source_type=SourceType.RSS,
        source_name="t",
        external_id="ext-1",
        title="t",
        url="https://x",
        author=None,
        published_at=datetime.now(UTC),
        content_text=content_text,
        summary=summary,
        tags=[],
        raw={},
        fetched_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_summarize_skips_when_summary_already_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_digest import pipeline as p

    repo = _CapturingArticleRepo(_article(summary="already done"))
    audit = _CapturingAuditRepo()

    called = False

    async def _fake_runner_run(agent, input):  # noqa: A002
        nonlocal called
        called = True
        return _FakeResult(_dummy_summary(), _Wrapper(_Usage()))

    monkeypatch.setattr("news_digest.pipeline.Runner.run", _fake_runner_run)

    out = await p.summarize_article(
        article_id=42,
        article_repo=repo,
        audit_writer=audit.insert,
        model="gpt-5.4-mini",
        max_content_chars=8000,
    )
    assert out["skipped"] is True
    assert called is False
    assert repo.updates == []
    assert audit.entries == []


@pytest.mark.asyncio
async def test_summarize_skips_when_no_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_digest import pipeline as p

    repo = _CapturingArticleRepo(_article(summary=None, content_text=None))
    audit = _CapturingAuditRepo()

    out = await p.summarize_article(
        article_id=42,
        article_repo=repo,
        audit_writer=audit.insert,
        model="gpt-5.4-mini",
        max_content_chars=8000,
    )
    assert out["skipped"] is True
    assert out["reason"] == "no content_text"
    assert repo.updates == []


@pytest.mark.asyncio
async def test_summarize_writes_summary_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_digest import pipeline as p

    repo = _CapturingArticleRepo(_article(summary=None))
    audit = _CapturingAuditRepo()
    canned = _dummy_summary()

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(canned, _Wrapper(_Usage()))

    monkeypatch.setattr("news_digest.pipeline.Runner.run", _fake_runner_run)

    out = await p.summarize_article(
        article_id=42,
        article_repo=repo,
        audit_writer=audit.insert,
        model="gpt-5.4-mini",
        max_content_chars=8000,
    )
    assert out["skipped"] is False
    assert repo.updates == [(42, canned.summary)]
    assert len(audit.entries) == 1
    entry = audit.entries[0]
    assert entry.metadata["article_id"] == 42
    assert entry.metadata["model"] == "gpt-5.4-mini"
    assert entry.metadata["input_tokens"] == 100


@pytest.mark.asyncio
async def test_summarize_returns_error_when_article_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_digest import pipeline as p

    repo = _CapturingArticleRepo(article=None)
    audit = _CapturingAuditRepo()

    out = await p.summarize_article(
        article_id=99,
        article_repo=repo,
        audit_writer=audit.insert,
        model="gpt-5.4-mini",
        max_content_chars=8000,
    )
    assert out["error"] == "not found"
    assert audit.entries == []


def _dummy_summary() -> DigestSummary:
    return DigestSummary(
        summary="A useful summary that is long enough to satisfy the schema. " * 2,
        key_takeaways=["one", "two"],
    )
```

- [ ] **Step 3.4.2: Run, expect failure**

```bash
uv run pytest services/agents/digest/src/news_digest/tests/unit/test_pipeline.py -v
```

- [ ] **Step 3.4.3: Implement `pipeline.py`**

```python
# services/agents/digest/src/news_digest/pipeline.py
"""Digest pipeline — summarise one article."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any, Protocol

from agents import Runner, trace
from news_observability.audit import AuditLogger
from news_observability.costs import extract_usage
from news_observability.logging import get_logger
from news_observability.validators import validate_structured_output
from news_schemas.agent_io import DigestSummary
from news_schemas.article import ArticleOut
from news_schemas.audit import AgentName, AuditLogIn, DecisionType

from news_digest.agent import build_agent, build_user_prompt

_log = get_logger("digest_pipeline")

AuditWriter = Callable[[AuditLogIn], Awaitable[None]]


class _ArticleRepo(Protocol):
    async def get_by_id(self, article_id: int) -> ArticleOut | None: ...
    async def update_summary(self, article_id: int, summary: str) -> None: ...


async def summarize_article(
    *,
    article_id: int,
    article_repo: _ArticleRepo,
    audit_writer: AuditWriter,
    model: str,
    max_content_chars: int,
) -> dict[str, Any]:
    """Summarise one article. Idempotent: skips when summary already populated."""

    article = await article_repo.get_by_id(article_id)
    if article is None:
        return {"article_id": article_id, "error": "not found"}
    if article.summary is not None:
        return {"article_id": article_id, "skipped": True}
    if not article.content_text:
        return {
            "article_id": article_id,
            "skipped": True,
            "reason": "no content_text",
        }

    agent = build_agent(model=model)
    prompt = build_user_prompt(
        title=article.title,
        url=str(article.url),
        source_type=article.source_type.value,
        source_name=article.source_name,
        content=article.content_text,
        max_chars=max_content_chars,
    )
    t0 = perf_counter()
    with trace(f"digest.{article_id}"):
        result = await Runner.run(agent, input=prompt)
    elapsed_ms = int((perf_counter() - t0) * 1000)

    digest = validate_structured_output(DigestSummary, result.final_output)
    usage = extract_usage(result, model=model)

    await article_repo.update_summary(article_id, digest.summary)

    audit = AuditLogger(audit_writer)
    await audit.log_decision(
        agent_name=AgentName.DIGEST,
        user_id=None,
        decision_type=DecisionType.SUMMARY,
        input_text=f"article {article_id}: {article.title}",
        output_text=digest.summary,
        metadata={
            "article_id": article_id,
            "key_takeaways": digest.key_takeaways,
            "model": usage.model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "requests": usage.requests,
            "estimated_cost_usd": usage.estimated_cost_usd,
            "duration_ms": elapsed_ms,
        },
    )

    return {
        "article_id": article_id,
        "summary": digest.summary,
        "skipped": False,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "duration_ms": elapsed_ms,
    }
```

Note: `validate_structured_output` accepts a dict OR a Pydantic model instance. The Agents SDK returns a parsed Pydantic instance when `output_type=` is set, so this call is a no-op type-check pass. Keep it for defense.

If the validators module rejects a Pydantic instance, fall back to:

```python
digest = result.final_output if isinstance(result.final_output, DigestSummary) else validate_structured_output(DigestSummary, result.final_output)
```

Run the existing validator tests to confirm behaviour before deciding.

- [ ] **Step 3.4.4: Run, expect pass**

```bash
uv run pytest services/agents/digest/src/news_digest/tests/unit/test_pipeline.py -v
uv run mypy services/agents/digest
```

- [ ] **Step 3.4.5: Commit**

```bash
git add services/agents/digest
git commit -m "feat(digest): summarize_article pipeline (skip+LLM+update+audit)"
```

---

### Task 3.5: `news_digest.cli` — Typer commands

**Files:**
- Create: [services/agents/digest/src/news_digest/cli.py](services/agents/digest/src/news_digest/cli.py)
- Create: [services/agents/digest/src/news_digest/__main__.py](services/agents/digest/src/news_digest/__main__.py)
- Create: [services/agents/digest/src/news_digest/tests/unit/test_cli.py](services/agents/digest/src/news_digest/tests/unit/test_cli.py)

- [ ] **Step 3.5.1: Write the failing test**

```python
# services/agents/digest/src/news_digest/tests/unit/test_cli.py
from __future__ import annotations

from typer.testing import CliRunner


def test_cli_help_includes_summarize_and_sweep() -> None:
    from news_digest.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "summarize" in result.stdout
    assert "sweep" in result.stdout
```

- [ ] **Step 3.5.2: Run, expect failure**

```bash
uv run pytest services/agents/digest/src/news_digest/tests/unit/test_cli.py -v
```

- [ ] **Step 3.5.3: Implement `cli.py` and `__main__.py`**

```python
# services/agents/digest/src/news_digest/cli.py
"""Local Typer CLI for the digest agent."""

from __future__ import annotations

import asyncio
import sys

import typer
from news_db.engine import get_session
from news_db.repositories.article_repo import ArticleRepository
from news_db.repositories.audit_log_repo import AuditLogRepository
from news_observability.logging import setup_logging

from news_digest.pipeline import summarize_article
from news_digest.settings import DigestSettings

app = typer.Typer(no_args_is_help=True, help="Digest agent CLI")


@app.command()
def summarize(article_id: int) -> None:
    """Summarise one article by ID."""

    async def _run() -> int:
        setup_logging()
        s = DigestSettings()
        async with get_session() as session:
            article_repo = ArticleRepository(session)
            audit_repo = AuditLogRepository(session)
            out = await summarize_article(
                article_id=article_id,
                article_repo=article_repo,
                audit_writer=audit_repo.insert,
                model=s.openai.model,
                max_content_chars=s.max_content_chars,
            )
        typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))


@app.command()
def sweep(hours: int = 24, limit: int = 50) -> None:
    """Summarise all unsummarised articles published within `hours`."""

    async def _run() -> int:
        setup_logging()
        s = DigestSettings()
        async with get_session() as session:
            article_repo = ArticleRepository(session)
            audit_repo = AuditLogRepository(session)
            pending = await article_repo.get_unsummarized(hours=hours, limit=limit)
            typer.echo(f"sweeping {len(pending)} unsummarised articles")
            for art in pending:
                out = await summarize_article(
                    article_id=art.id,
                    article_repo=article_repo,
                    audit_writer=audit_repo.insert,
                    model=s.openai.model,
                    max_content_chars=s.max_content_chars,
                )
                typer.echo(f"{art.id}: {out.get('skipped', False)}")
        return 0

    sys.exit(asyncio.run(_run()))
```

```python
# services/agents/digest/src/news_digest/__main__.py
from news_digest.cli import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 3.5.4: Run, expect pass**

```bash
uv run pytest services/agents/digest/src/news_digest/tests/unit/test_cli.py -v
```

- [ ] **Step 3.5.5: Commit**

```bash
git add services/agents/digest
git commit -m "feat(digest): Typer CLI (summarize + sweep)"
```

---

### Task 3.6: `lambda_handler.py`

**Files:**
- Create: [services/agents/digest/lambda_handler.py](services/agents/digest/lambda_handler.py)
- Create: [services/agents/digest/src/news_digest/tests/unit/test_lambda_handler.py](services/agents/digest/src/news_digest/tests/unit/test_lambda_handler.py)
- Create: [packages/config/src/news_config/lambda_settings.py](packages/config/src/news_config/lambda_settings.py)
- Create: [packages/config/src/news_config/tests/test_lambda_settings.py](packages/config/src/news_config/tests/test_lambda_settings.py)

- [ ] **Step 3.6.1: Write `lambda_settings` tests**

```python
# packages/config/src/news_config/tests/test_lambda_settings.py
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_load_settings_skips_when_db_url_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")
    from news_config.lambda_settings import load_settings_from_ssm

    fake = MagicMock()
    load_settings_from_ssm(prefix="/news-aggregator/dev", ssm_client=fake)
    fake.get_parameters_by_path.assert_not_called()


def test_load_settings_populates_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from news_config.lambda_settings import load_settings_from_ssm

    fake = MagicMock()
    fake.get_parameters_by_path.return_value = {
        "Parameters": [
            {"Name": "/news-aggregator/dev/openai_api_key", "Value": "sk-1"},  # pragma: allowlist secret
            {"Name": "/news-aggregator/dev/supabase_db_url", "Value": "url"},
        ]
    }
    load_settings_from_ssm(prefix="/news-aggregator/dev", ssm_client=fake)
    import os

    assert os.environ["OPENAI_API_KEY"] == "sk-1"  # pragma: allowlist secret
    assert os.environ["SUPABASE_DB_URL"] == "url"
```

- [ ] **Step 3.6.2: Run, expect failure**

```bash
uv run pytest packages/config/src/news_config/tests/test_lambda_settings.py -v
```

- [ ] **Step 3.6.3: Implement `lambda_settings.py`**

```python
# packages/config/src/news_config/lambda_settings.py
"""Cold-start helper to read SSM SecureStrings into env vars (Lambda)."""

from __future__ import annotations

import os
from typing import Any

from news_observability.logging import get_logger

_log = get_logger("lambda_settings")


def load_settings_from_ssm(
    *,
    prefix: str,
    ssm_client: Any | None = None,
) -> None:
    """Populate env vars from an SSM parameter tree.

    Idempotent: bails out as soon as one canary env var (SUPABASE_DB_URL) is
    set. Pass an explicit `ssm_client` to mock during tests.

    Calls `os.environ.setdefault` so existing env vars (e.g. local .env) win.
    """
    if os.environ.get("SUPABASE_DB_URL"):
        return

    if ssm_client is None:
        import boto3  # local import — keeps pure-Python tests fast

        ssm_client = boto3.client("ssm")

    resp = ssm_client.get_parameters_by_path(
        Path=prefix, WithDecryption=True, Recursive=True
    )
    for p in resp.get("Parameters", []):
        env_key = p["Name"].rsplit("/", 1)[-1].upper()
        os.environ.setdefault(env_key, p["Value"])
    _log.info("loaded {} ssm params from {}", len(resp.get("Parameters", [])), prefix)
```

- [ ] **Step 3.6.4: Run, expect pass**

```bash
uv run pytest packages/config/src/news_config/tests/test_lambda_settings.py -v
```

- [ ] **Step 3.6.5: Write the lambda handler test**

```python
# services/agents/digest/src/news_digest/tests/unit/test_lambda_handler.py
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_handler_calls_summarize(monkeypatch: pytest.MonkeyPatch) -> None:
    """The handler bridges Lambda's sync invocation to our async pipeline."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")  # short-circuit ssm

    captured = {}

    async def _fake_pipeline(*, article_id, article_repo, audit_writer, model, max_content_chars):
        captured["article_id"] = article_id
        captured["model"] = model
        return {"article_id": article_id, "skipped": False}

    monkeypatch.setattr("news_digest.pipeline.summarize_article", _fake_pipeline)

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

    def _fake_get_session():
        return _FakeSession()

    monkeypatch.setattr("news_db.engine.get_session", _fake_get_session)
    monkeypatch.setattr(
        "news_db.repositories.article_repo.ArticleRepository", lambda s: object()
    )
    monkeypatch.setattr(
        "news_db.repositories.audit_log_repo.AuditLogRepository",
        lambda s: type("R", (), {"insert": lambda self, e: None})(),
    )

    import lambda_handler  # noqa: PLC0415

    out = lambda_handler.handler({"article_id": 42}, None)
    assert out["article_id"] == 42
    assert captured["article_id"] == 42
```

- [ ] **Step 3.6.6: Implement `lambda_handler.py`**

```python
# services/agents/digest/lambda_handler.py
"""AWS Lambda entry point for the digest agent.

Cold-start: reads SSM params into env vars, configures logging + tracing.
Warm-start: re-uses cached env vars and the Agents SDK client.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

# Pre-init: hydrate env from SSM before any other module reads settings.
from news_config.lambda_settings import load_settings_from_ssm

load_settings_from_ssm(prefix=os.environ.get("SSM_PARAM_PREFIX", "/news-aggregator/dev"))

from news_db.engine import get_session  # noqa: E402
from news_db.repositories.article_repo import ArticleRepository  # noqa: E402
from news_db.repositories.audit_log_repo import AuditLogRepository  # noqa: E402
from news_observability.logging import setup_logging  # noqa: E402
from news_observability.tracing import configure_tracing  # noqa: E402

from news_digest import pipeline  # noqa: E402
from news_digest.settings import DigestSettings  # noqa: E402

setup_logging()
configure_tracing(enable_langfuse=True)


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Lambda entry. `event = {"article_id": int}`."""
    article_id = int(event["article_id"])
    return asyncio.run(_run(article_id))


async def _run(article_id: int) -> dict[str, Any]:
    settings = DigestSettings()
    async with get_session() as session:
        article_repo = ArticleRepository(session)
        audit_repo = AuditLogRepository(session)
        return await pipeline.summarize_article(
            article_id=article_id,
            article_repo=article_repo,
            audit_writer=audit_repo.insert,
            model=settings.openai.model,
            max_content_chars=settings.max_content_chars,
        )
```

- [ ] **Step 3.6.7: Run, expect pass**

```bash
uv run pytest services/agents/digest/src/news_digest/tests -v
uv run mypy packages/config services/agents/digest
```

- [ ] **Step 3.6.8: Commit**

```bash
git add packages/config services/agents/digest/lambda_handler.py services/agents/digest/src/news_digest/tests/unit/test_lambda_handler.py
git commit -m "feat(digest): lambda_handler + load_settings_from_ssm cold-start helper"
```

---

### Task 3.7: `package_docker.py` for the digest agent

**Files:**
- Create: [services/agents/digest/package_docker.py](services/agents/digest/package_docker.py)

- [ ] **Step 3.7.1: Implement `package_docker.py`**

This script builds the zip inside `public.ecr.aws/lambda/python:3.12` so wheels are linux/amd64 manylinux. Mirrors the alex-multi-agent-saas/backend/reporter pattern.

```python
# services/agents/digest/package_docker.py
"""Build a Lambda zip artifact for the digest agent.

Uses public.ecr.aws/lambda/python:3.12 as the build image so wheels are amd64
manylinux. Output: services/agents/digest/dist/news_digest.zip.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_DIR = Path(__file__).resolve().parent
DIST = AGENT_DIR / "dist"
PACKAGE_NAME = "news_digest"


_DOCKERFILE = """
FROM public.ecr.aws/lambda/python:3.12 AS build

WORKDIR /work
RUN dnf install -y zip && dnf clean all

COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY services/agents/{agent}/ ./services/agents/{agent}/

# uv from astral
COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /usr/local/bin/uv

RUN uv export --no-dev --no-emit-workspace --package {package} --frozen \\
        --format requirements-txt > /tmp/req.txt
RUN python -m pip install -r /tmp/req.txt --target /pkg --no-cache-dir
# Copy first-party workspace packages too (they aren't on PyPI).
RUN cp -r packages/schemas/src/news_schemas /pkg/ \\
 && cp -r packages/config/src/news_config /pkg/ \\
 && cp -r packages/observability/src/news_observability /pkg/ \\
 && cp -r packages/db/src/news_db /pkg/ \\
 && cp -r services/agents/{agent}/src/{package} /pkg/ \\
 && cp services/agents/{agent}/lambda_handler.py /pkg/lambda_handler.py

WORKDIR /pkg
RUN zip -r9 /tmp/{package}.zip . -x '*.pyc' '__pycache__/*'

FROM scratch AS export
COPY --from=build /tmp/{package}.zip /
"""


def main() -> int:
    if shutil.which("docker") is None:
        print("ERROR: docker not found", file=sys.stderr)
        return 2

    DIST.mkdir(parents=True, exist_ok=True)
    dockerfile = AGENT_DIR / ".package.Dockerfile"
    dockerfile.write_text(
        _DOCKERFILE.format(agent=AGENT_DIR.name, package=PACKAGE_NAME)
    )

    cmd = [
        "docker",
        "build",
        "--platform=linux/amd64",
        "--target=export",
        "--output",
        f"type=local,dest={DIST}",
        "-f",
        str(dockerfile),
        str(REPO_ROOT),
    ]
    subprocess.run(cmd, check=True)
    print(f"built: {DIST / (PACKAGE_NAME + '.zip')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3.7.2: Smoke-test the build locally**

```bash
uv run python services/agents/digest/package_docker.py
ls -lh services/agents/digest/dist/news_digest.zip
```

Expected: zip created, ~70–100 MB.

- [ ] **Step 3.7.3: Add `dist/` and `.package.Dockerfile` to `.gitignore`**

Append to root `.gitignore`:

```
services/agents/*/dist/
services/agents/*/.package.Dockerfile
```

- [ ] **Step 3.7.4: Commit**

```bash
git add services/agents/digest/package_docker.py .gitignore
git commit -m "build(digest): package_docker.py — zip artifact via lambda/python:3.12"
```

---

### Task 3.8: Phase 3 verification

- [ ] **Step 3.8.1: Run full check**

```bash
uv run ruff check
uv run mypy packages services/agents/digest
uv run pytest -q
```

All green. Phase 3 (digest agent code) done.

---

## Phase 4 — Editor agent

Same shape as digest. We add `prompts.py` because the editor system prompt embeds the user profile and is worth snapshot-testing.

### Task 4.1: Workspace package + settings

- [ ] **Step 4.1.1: Create `services/agents/editor/pyproject.toml`**

```toml
[project]
name = "news_editor"
version = "0.1.0"
requires-python = ">=3.12"
description = "Editor agent — per-user article ranking Lambda"
dependencies = [
    "openai-agents>=0.14.5",
    "pydantic>=2.13.3",
    "pydantic-settings>=2.5",
    "loguru>=0.7.3",
    "typer>=0.24.2",
    "boto3>=1.42.95",
    "news_schemas",
    "news_config",
    "news_observability",
    "news_db",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/news_editor"]
```

- [ ] **Step 4.1.2: Create `__init__.py` and add to root workspace**

```python
# services/agents/editor/src/news_editor/__init__.py
"""Editor agent — per-user article ranking."""
```

Edit root `pyproject.toml` `[tool.uv.workspace] members` and `[tool.uv.sources]` to include `services/agents/editor` and `news_editor`.

- [ ] **Step 4.1.3: Sync + commit**

```bash
uv sync --all-packages
git add services/agents/editor pyproject.toml uv.lock
git commit -m "feat(editor): scaffold news_editor workspace package"
```

- [ ] **Step 4.1.4: Add `EditorSettings` (TDD)**

Write `services/agents/editor/src/news_editor/tests/unit/test_settings.py` mirroring 3.2.1, then implement:

```python
# services/agents/editor/src/news_editor/settings.py
from __future__ import annotations

from news_config.settings import OpenAISettings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EditorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    candidate_limit: int = Field(default=100, alias="EDITOR_CANDIDATE_LIMIT")
    top_n: int = Field(default=10, alias="EDITOR_TOP_N")
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
```

Test, verify pass, commit:

```bash
git add services/agents/editor
git commit -m "feat(editor): EditorSettings"
```

---

### Task 4.2: `news_editor.prompts` — system + candidate prompt builders

**Files:**
- Create: [services/agents/editor/src/news_editor/prompts.py](services/agents/editor/src/news_editor/prompts.py)
- Create: [services/agents/editor/src/news_editor/tests/unit/test_prompts.py](services/agents/editor/src/news_editor/tests/unit/test_prompts.py)

- [ ] **Step 4.2.1: Write the failing tests (snapshot-style)**

```python
# services/agents/editor/src/news_editor/tests/unit/test_prompts.py
from __future__ import annotations

from news_schemas.user_profile import (
    Interests,
    Preferences,
    ReadingTime,
    UserProfile,
)


def _profile() -> UserProfile:
    return UserProfile(
        background=["software engineer", "AI"],
        interests=Interests(
            primary=["agents", "RAG"],
            secondary=["voice"],
            specific_topics=["multi-agent orchestration"],
        ),
        preferences=Preferences(
            content_type=["technical", "deep-dive"],
            avoid=["funding-only news"],
        ),
        goals=["build production agents"],
        reading_time=ReadingTime(daily_limit="20 min", preferred_article_count="5"),
    )


def test_system_prompt_embeds_profile_fields() -> None:
    from news_editor.prompts import build_system_prompt

    p = build_system_prompt(_profile(), email_name="Pat")
    assert "Pat" in p
    assert "agents" in p
    assert "production agents" in p
    assert "funding-only news" in p
    assert "0-100" in p or "0 to 100" in p


def test_candidate_prompt_lists_articles() -> None:
    from news_editor.prompts import build_candidate_prompt

    candidates = [
        {"id": 1, "title": "T1", "summary": "S1", "source_name": "src", "url": "u1"},
        {"id": 2, "title": "T2", "summary": "S2", "source_name": "src", "url": "u2"},
    ]
    p = build_candidate_prompt(candidates)
    assert "1" in p and "2" in p
    assert "T1" in p and "T2" in p
    assert "S1" in p
```

- [ ] **Step 4.2.2: Run, expect failure**

- [ ] **Step 4.2.3: Implement `prompts.py`**

```python
# services/agents/editor/src/news_editor/prompts.py
"""System prompt + candidate prompt for the editor agent."""

from __future__ import annotations

from typing import Any

from news_observability.sanitizer import sanitize_prompt_input
from news_schemas.user_profile import UserProfile


def build_system_prompt(profile: UserProfile, *, email_name: str) -> str:
    return (
        f"You are a personalised AI news editor for {email_name}.\n\n"
        f"Reader profile:\n"
        f"- Background: {', '.join(profile.background) or 'n/a'}\n"
        f"- Primary interests: {', '.join(profile.interests.primary) or 'n/a'}\n"
        f"- Secondary interests: {', '.join(profile.interests.secondary) or 'n/a'}\n"
        f"- Specific topics: {', '.join(profile.interests.specific_topics) or 'n/a'}\n"
        f"- Preferred content: {', '.join(profile.preferences.content_type) or 'any'}\n"
        f"- Avoid: {', '.join(profile.preferences.avoid) or 'nothing'}\n"
        f"- Goals: {', '.join(profile.goals) or 'n/a'}\n"
        f"- Reading time: {profile.reading_time.daily_limit}\n\n"
        "Score every candidate article on a 0-100 scale (relevance to the "
        "reader's profile and goals). Emit `rankings` (one entry per article), "
        "`top_themes` (up to 10 short phrases describing the day's pattern), "
        "and a brief `overall_summary`.\n\n"
        "Rules:\n"
        "- Only return article_ids that appeared in the candidate list.\n"
        "- `why_ranked` is 1-2 sentences explaining the score for that reader.\n"
        "- Penalise items that match `avoid`. Reward items that match interests "
        "AND content preferences.\n"
        "- Be ruthless: there should be a wide score spread."
    )


def build_candidate_prompt(candidates: list[dict[str, Any]]) -> str:
    """Build the candidate-list prompt for the editor agent.

    Sanitises *title*, *summary*, *source_name* per AGENTS.md prompt-injection
    invariant — these are scraped third-party text. Hard-block patterns raise
    PromptInjectionError; soft-block patterns are silently redacted.
    """
    lines = ["Candidates (id | source | title | summary):"]
    for c in candidates:
        title = sanitize_prompt_input((c.get("title") or "").strip())
        summary = sanitize_prompt_input((c.get("summary") or "").strip())
        source = sanitize_prompt_input(c.get("source_name") or "")
        lines.append(f"- {c['id']} | {source} | {title} | {summary}")
    lines.append("")
    lines.append("Score each. Use the article_id field exactly as given.")
    return "\n".join(lines)
```

- [ ] **Step 4.2.4: Run, expect pass; commit**

```bash
uv run pytest services/agents/editor/src/news_editor/tests/unit/test_prompts.py -v
git add services/agents/editor
git commit -m "feat(editor): build_system_prompt + build_candidate_prompt"
```

---

### Task 4.3: `news_editor.agent` — `build_agent`

**Files:**
- Create: [services/agents/editor/src/news_editor/agent.py](services/agents/editor/src/news_editor/agent.py)
- Create: [services/agents/editor/src/news_editor/tests/unit/test_agent.py](services/agents/editor/src/news_editor/tests/unit/test_agent.py)

- [ ] **Step 4.3.1: Write the failing test**

Same shape as 3.3.1 — assert `agent.output_type is EditorDecision`, `agent.name == "EditorAgent"`, and `agent.model == "gpt-5.4-mini"` (string passthrough; no `OpenAIChatCompletionsModel` wrapping). Pass a stub `UserProfile` (use `_profile()` helper from the prompts test).

- [ ] **Step 4.3.2: Run, expect failure; implement**

```python
# services/agents/editor/src/news_editor/agent.py
from __future__ import annotations

from agents import Agent
from news_schemas.agent_io import EditorDecision
from news_schemas.user_profile import UserProfile

from news_editor.prompts import build_system_prompt


def build_agent(*, profile: UserProfile, email_name: str, model: str) -> Agent[EditorDecision]:
    return Agent(
        name="EditorAgent",
        instructions=build_system_prompt(profile, email_name=email_name),
        model=model,
        output_type=EditorDecision,
    )
```

- [ ] **Step 4.3.3: Pass + commit**

```bash
uv run pytest services/agents/editor/src/news_editor/tests/unit/test_agent.py -v
git add services/agents/editor
git commit -m "feat(editor): build_agent"
```

---

### Task 4.4: `news_editor.pipeline` — `rank_for_user`

**Files:**
- Create: [services/agents/editor/src/news_editor/pipeline.py](services/agents/editor/src/news_editor/pipeline.py)
- Create: [services/agents/editor/src/news_editor/tests/unit/test_pipeline.py](services/agents/editor/src/news_editor/tests/unit/test_pipeline.py)

- [ ] **Step 4.4.1: Write the failing tests**

Cover three behaviours:
1. Empty candidates → digest row written with `status=FAILED`, no LLM call.
2. Hallucinated `article_id`s in rankings → dropped silently; top-10 from valid set; digest written with status `GENERATED`.
3. Happy path → top scores wins; `RankedArticle` fields populated from DB rows; audit row written.

```python
# services/agents/editor/src/news_editor/tests/unit/test_pipeline.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from news_schemas.agent_io import ArticleRanking, EditorDecision
from news_schemas.article import ArticleOut, SourceType
from news_schemas.audit import AuditLogIn
from news_schemas.digest import DigestIn, DigestOut, DigestStatus
from news_schemas.user_profile import (
    Interests,
    Preferences,
    ReadingTime,
    UserOut,
    UserProfile,
)


@dataclass
class _Usage:
    input_tokens: int = 200
    output_tokens: int = 100
    total_tokens: int = 300
    requests: int = 1


@dataclass
class _Wrapper:
    usage: _Usage


@dataclass
class _FakeResult:
    final_output: EditorDecision
    context_wrapper: _Wrapper


def _profile() -> UserProfile:
    return UserProfile(
        background=["dev"],
        interests=Interests(primary=["agents"]),
        preferences=Preferences(),
        goals=[],
        reading_time=ReadingTime(daily_limit="20m", preferred_article_count="5"),
    )


def _user(uid: UUID) -> UserOut:
    return UserOut(
        id=uid,
        clerk_user_id="c-1",
        email="t@example.com",
        name="t",
        email_name="Pat",
        profile=_profile(),
        profile_completed_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _article(aid: int) -> ArticleOut:
    return ArticleOut(
        id=aid,
        source_type=SourceType.RSS,
        source_name="src",
        external_id=f"ext-{aid}",
        title=f"T{aid}",
        url=f"https://x/{aid}",
        author=None,
        published_at=datetime.now(UTC),
        content_text="c",
        summary=f"summary {aid}",
        tags=[],
        raw={},
        fetched_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class _CapturingDigestRepo:
    def __init__(self) -> None:
        self.created: list[DigestIn] = []
        self._next_id = 100

    async def create(self, d: DigestIn) -> DigestOut:
        self.created.append(d)
        out = DigestOut(
            id=self._next_id,
            user_id=d.user_id,
            period_start=d.period_start,
            period_end=d.period_end,
            intro=d.intro,
            ranked_articles=d.ranked_articles,
            top_themes=d.top_themes,
            article_count=d.article_count,
            status=d.status,
            error_message=d.error_message,
            generated_at=datetime.now(UTC),
        )
        self._next_id += 1
        return out


class _ArticleRepo:
    def __init__(self, rows: list[ArticleOut]) -> None:
        self._rows = rows

    async def get_recent_with_summaries(self, hours: int, limit: int) -> list[ArticleOut]:
        return self._rows[:limit]


class _UserRepo:
    def __init__(self, user: UserOut | None) -> None:
        self._user = user

    async def get_by_id(self, user_id: UUID) -> UserOut | None:
        return self._user


class _AuditRepo:
    def __init__(self) -> None:
        self.entries: list[AuditLogIn] = []

    async def insert(self, e: AuditLogIn) -> None:
        self.entries.append(e)


@pytest.mark.asyncio
async def test_rank_for_user_no_candidates_writes_failed_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_editor import pipeline

    uid = uuid4()
    digests = _CapturingDigestRepo()

    out = await pipeline.rank_for_user(
        user_id=uid,
        article_repo=_ArticleRepo([]),
        user_repo=_UserRepo(_user(uid)),
        digest_repo=digests,
        audit_writer=_AuditRepo().insert,
        model="gpt-5.4-mini",
        lookback_hours=24,
        limit=100,
        top_n=10,
    )
    assert digests.created[0].status is DigestStatus.FAILED
    assert digests.created[0].error_message == "no candidates"
    assert out["digest_id"] == 100


@pytest.mark.asyncio
async def test_rank_for_user_drops_hallucinated_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_editor import pipeline

    uid = uuid4()
    candidates = [_article(1), _article(2)]

    canned = EditorDecision(
        rankings=[
            ArticleRanking(article_id=1, score=80, why_ranked="ten chars long"),
            ArticleRanking(article_id=999, score=99, why_ranked="ten chars long"),
            ArticleRanking(article_id=2, score=60, why_ranked="ten chars long"),
        ],
        top_themes=["t"],
        overall_summary="",
    )

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(canned, _Wrapper(_Usage()))

    monkeypatch.setattr("news_editor.pipeline.Runner.run", _fake_runner_run)

    digests = _CapturingDigestRepo()
    audit = _AuditRepo()
    out = await pipeline.rank_for_user(
        user_id=uid,
        article_repo=_ArticleRepo(candidates),
        user_repo=_UserRepo(_user(uid)),
        digest_repo=digests,
        audit_writer=audit.insert,
        model="gpt-5.4-mini",
        lookback_hours=24,
        limit=100,
        top_n=10,
    )
    assert digests.created[0].status is DigestStatus.GENERATED
    ids = [r.article_id for r in digests.created[0].ranked_articles]
    assert 999 not in ids
    assert ids == [1, 2]
    assert audit.entries
```

- [ ] **Step 4.4.2: Run, expect failure**

- [ ] **Step 4.4.3: Implement `pipeline.py`**

```python
# services/agents/editor/src/news_editor/pipeline.py
"""Editor pipeline — score candidates and write a `digests` row."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any, Protocol
from uuid import UUID

from agents import Runner, trace
from news_observability.audit import AuditLogger
from news_observability.costs import extract_usage
from news_observability.logging import get_logger
from news_observability.validators import validate_structured_output
from news_schemas.agent_io import EditorDecision
from news_schemas.article import ArticleOut
from news_schemas.audit import AgentName, AuditLogIn, DecisionType
from news_schemas.digest import DigestIn, DigestOut, DigestStatus, RankedArticle
from news_schemas.user_profile import UserOut

from news_editor.agent import build_agent
from news_editor.prompts import build_candidate_prompt

_log = get_logger("editor_pipeline")
AuditWriter = Callable[[AuditLogIn], Awaitable[None]]


class _ArticleRepo(Protocol):
    async def get_recent_with_summaries(
        self, hours: int, limit: int
    ) -> list[ArticleOut]: ...


class _UserRepo(Protocol):
    async def get_by_id(self, user_id: UUID) -> UserOut | None: ...


class _DigestRepo(Protocol):
    async def create(self, item: DigestIn) -> DigestOut: ...


async def rank_for_user(
    *,
    user_id: UUID,
    article_repo: _ArticleRepo,
    user_repo: _UserRepo,
    digest_repo: _DigestRepo,
    audit_writer: AuditWriter,
    model: str,
    lookback_hours: int,
    limit: int,
    top_n: int,
) -> dict[str, Any]:
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise ValueError(f"user {user_id} not found")

    period_end = datetime.now(UTC)
    period_start = period_end - timedelta(hours=lookback_hours)

    candidates = await article_repo.get_recent_with_summaries(
        hours=lookback_hours, limit=limit
    )

    if not candidates:
        digest = await digest_repo.create(
            DigestIn(
                user_id=user_id,
                period_start=period_start,
                period_end=period_end,
                ranked_articles=[],
                article_count=0,
                status=DigestStatus.FAILED,
                error_message="no candidates",
            )
        )
        return {"digest_id": digest.id, "status": DigestStatus.FAILED.value}

    agent = build_agent(profile=user.profile, email_name=user.email_name, model=model)
    prompt_payload = [
        {
            "id": a.id,
            "title": a.title,
            "summary": a.summary or "",
            "source_name": a.source_name,
            "url": a.url,
        }
        for a in candidates
    ]
    prompt = build_candidate_prompt(prompt_payload)

    t0 = perf_counter()
    with trace(f"editor.user.{user_id}"):
        result = await Runner.run(agent, input=prompt)
    elapsed_ms = int((perf_counter() - t0) * 1000)

    decision = validate_structured_output(EditorDecision, result.final_output)
    usage = extract_usage(result, model=model)

    by_id = {a.id: a for a in candidates}
    valid = [r for r in decision.rankings if r.article_id in by_id]
    if len(valid) < len(decision.rankings):
        _log.warning(
            "dropped {} hallucinated article_ids",
            len(decision.rankings) - len(valid),
        )
    top = sorted(valid, key=lambda r: r.score, reverse=True)[:top_n]

    ranked = [
        RankedArticle(
            article_id=r.article_id,
            score=r.score,
            title=by_id[r.article_id].title,
            url=by_id[r.article_id].url,  # type: ignore[arg-type]
            summary=by_id[r.article_id].summary or "",
            why_ranked=r.why_ranked,
        )
        for r in top
    ]

    digest_status = DigestStatus.GENERATED if ranked else DigestStatus.FAILED
    digest = await digest_repo.create(
        DigestIn(
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
            ranked_articles=ranked,
            top_themes=decision.top_themes,
            article_count=len(candidates),
            status=digest_status,
            error_message=None if ranked else "no valid rankings",
        )
    )

    audit = AuditLogger(audit_writer)
    await audit.log_decision(
        agent_name=AgentName.EDITOR,
        user_id=user_id,
        decision_type=DecisionType.RANK,
        input_text=f"user {user_id}: ranking {len(candidates)} candidates",
        output_text=(
            f"top pick art {top[0].article_id if top else None}; "
            f"themes {decision.top_themes}"
        ),
        metadata={
            "user_id": str(user_id),
            "candidate_count": len(candidates),
            "top_pick_id": top[0].article_id if top else None,
            "top_themes": decision.top_themes,
            "model": usage.model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "requests": usage.requests,
            "estimated_cost_usd": usage.estimated_cost_usd,
            "duration_ms": elapsed_ms,
        },
    )

    return {"digest_id": digest.id, "status": digest_status.value, "ranked": len(ranked)}
```

- [ ] **Step 4.4.4: Run, expect pass; commit**

```bash
uv run pytest services/agents/editor/src/news_editor/tests/unit/test_pipeline.py -v
uv run mypy services/agents/editor
git add services/agents/editor
git commit -m "feat(editor): rank_for_user pipeline (candidates → ranked digest)"
```

---

### Task 4.5: Editor CLI + lambda_handler

**Files:**
- Create: [services/agents/editor/src/news_editor/cli.py](services/agents/editor/src/news_editor/cli.py)
- Create: [services/agents/editor/src/news_editor/__main__.py](services/agents/editor/src/news_editor/__main__.py)
- Create: [services/agents/editor/lambda_handler.py](services/agents/editor/lambda_handler.py)
- Create: [services/agents/editor/src/news_editor/tests/unit/test_cli.py](services/agents/editor/src/news_editor/tests/unit/test_cli.py)
- Create: [services/agents/editor/src/news_editor/tests/unit/test_lambda_handler.py](services/agents/editor/src/news_editor/tests/unit/test_lambda_handler.py)

- [ ] **Step 4.5.1: Write CLI/handler tests** (mirror digest 3.5/3.6 — assert help text, assert handler invokes pipeline with the user_id from the event, assert SSM cold-start guard runs).

Event shape: `{"user_id": "<uuid>", "lookback_hours": 24}`.

- [ ] **Step 4.5.2: Implement `cli.py`**

```python
# services/agents/editor/src/news_editor/cli.py
from __future__ import annotations

import asyncio
import sys
from uuid import UUID

import typer
from news_db.engine import get_session
from news_db.repositories.article_repo import ArticleRepository
from news_db.repositories.audit_log_repo import AuditLogRepository
from news_db.repositories.digest_repo import DigestRepository
from news_db.repositories.user_repo import UserRepository
from news_observability.logging import setup_logging

from news_editor.pipeline import rank_for_user
from news_editor.settings import EditorSettings

app = typer.Typer(no_args_is_help=True, help="Editor agent CLI")


@app.command()
def rank(user_id: UUID, hours: int = 24) -> None:
    """Rank recent articles for a user; writes a `digests` row."""

    async def _run() -> int:
        setup_logging()
        s = EditorSettings()
        async with get_session() as session:
            out = await rank_for_user(
                user_id=user_id,
                article_repo=ArticleRepository(session),
                user_repo=UserRepository(session),
                digest_repo=DigestRepository(session),
                audit_writer=AuditLogRepository(session).insert,
                model=s.openai.model,
                lookback_hours=hours,
                limit=s.candidate_limit,
                top_n=s.top_n,
            )
        typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))
```

`__main__.py`: `from news_editor.cli import app; app()`

- [ ] **Step 4.5.3: Implement `lambda_handler.py`**

```python
# services/agents/editor/lambda_handler.py
from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import UUID

from news_config.lambda_settings import load_settings_from_ssm

load_settings_from_ssm(prefix=os.environ.get("SSM_PARAM_PREFIX", "/news-aggregator/dev"))

from news_db.engine import get_session  # noqa: E402
from news_db.repositories.article_repo import ArticleRepository  # noqa: E402
from news_db.repositories.audit_log_repo import AuditLogRepository  # noqa: E402
from news_db.repositories.digest_repo import DigestRepository  # noqa: E402
from news_db.repositories.user_repo import UserRepository  # noqa: E402
from news_observability.logging import setup_logging  # noqa: E402
from news_observability.tracing import configure_tracing  # noqa: E402

from news_editor.pipeline import rank_for_user  # noqa: E402
from news_editor.settings import EditorSettings  # noqa: E402

setup_logging()
configure_tracing(enable_langfuse=True)


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    user_id = UUID(event["user_id"])
    lookback_hours = int(event.get("lookback_hours", 24))
    return asyncio.run(_run(user_id, lookback_hours))


async def _run(user_id: UUID, lookback_hours: int) -> dict[str, Any]:
    s = EditorSettings()
    async with get_session() as session:
        return await rank_for_user(
            user_id=user_id,
            article_repo=ArticleRepository(session),
            user_repo=UserRepository(session),
            digest_repo=DigestRepository(session),
            audit_writer=AuditLogRepository(session).insert,
            model=s.openai.model,
            lookback_hours=lookback_hours,
            limit=s.candidate_limit,
            top_n=s.top_n,
        )
```

- [ ] **Step 4.5.4: Run all editor tests, expect pass; commit**

```bash
uv run pytest services/agents/editor -v
git add services/agents/editor
git commit -m "feat(editor): Typer CLI + lambda_handler"
```

---

### Task 4.6: Editor `package_docker.py`

- [ ] **Step 4.6.1: Copy + adapt the digest version**

Same code as 3.7.1, with `PACKAGE_NAME = "news_editor"` and `AGENT_DIR = services/agents/editor`. The Dockerfile template uses `AGENT_DIR.name`/`PACKAGE_NAME` placeholders so the only change is those two constants.

- [ ] **Step 4.6.2: Smoke build**

```bash
uv run python services/agents/editor/package_docker.py
ls -lh services/agents/editor/dist/news_editor.zip
```

- [ ] **Step 4.6.3: Commit**

```bash
git add services/agents/editor/package_docker.py
git commit -m "build(editor): package_docker.py"
```

---

## Phase 5 — Email agent

This phase ships three sub-modules beyond the pattern: a Resend HTTP client, a Jinja2 renderer, and a digest HTML template. Compose mode = LLM produces intro + subject; deterministic Python sends.

### Task 5.1: Workspace package + settings + Resend dep

- [ ] **Step 5.1.1: Create `services/agents/email/pyproject.toml`**

```toml
[project]
name = "news_email"
version = "0.1.0"
requires-python = ">=3.12"
description = "Email agent — intro composer + Resend send Lambda"
dependencies = [
    "openai-agents>=0.14.5",
    "pydantic>=2.13.3",
    "pydantic-settings>=2.5",
    "loguru>=0.7.3",
    "typer>=0.24.2",
    "boto3>=1.42.95",
    "httpx>=0.28.1",
    "jinja2>=3.1",
    "news_schemas",
    "news_config",
    "news_observability",
    "news_db",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/news_email"]
```

- [ ] **Step 5.1.2: Add to root workspace + sync + commit**

```bash
uv sync --all-packages
git add services/agents/email/pyproject.toml services/agents/email/src/news_email/__init__.py pyproject.toml uv.lock
git commit -m "feat(email): scaffold news_email workspace package"
```

- [ ] **Step 5.1.3: Implement `EmailSettings` (TDD)**

```python
# services/agents/email/src/news_email/settings.py
from __future__ import annotations

from news_config.settings import MailSettings, OpenAISettings, ResendSettings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    resend: ResendSettings = Field(default_factory=ResendSettings)
    mail: MailSettings = Field(default_factory=MailSettings)
```

Test, pass, commit:

```bash
git add services/agents/email
git commit -m "feat(email): EmailSettings (openai + resend + mail)"
```

---

### Task 5.2: `news_email.resend_client` — HTTP wrapper

**Files:**
- Create: [services/agents/email/src/news_email/resend_client.py](services/agents/email/src/news_email/resend_client.py)
- Create: [services/agents/email/src/news_email/tests/unit/test_resend_client.py](services/agents/email/src/news_email/tests/unit/test_resend_client.py)

- [ ] **Step 5.2.1: Write tests using `httpx.MockTransport`**

```python
# services/agents/email/src/news_email/tests/unit/test_resend_client.py
from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_send_via_resend_returns_message_id() -> None:
    from news_email.resend_client import send_via_resend

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.resend.com"
        body = request.read()
        assert b'"to":["t@example.com"]' in body
        return httpx.Response(200, json={"id": "msg-1"})

    transport = httpx.MockTransport(handler)
    out = await send_via_resend(
        api_key="sk-1",  # pragma: allowlist secret
        sender_name="AI News",
        mail_from="hi@news.example",
        to="t@example.com",
        subject="hi",
        html="<p>hi</p>",
        transport=transport,
    )
    assert out["id"] == "msg-1"


@pytest.mark.asyncio
async def test_send_via_resend_raises_on_401() -> None:
    from news_email.resend_client import send_via_resend

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "auth"})

    transport = httpx.MockTransport(handler)
    with pytest.raises(RuntimeError, match="authentication"):
        await send_via_resend(
            api_key="bad",  # pragma: allowlist secret
            sender_name="x",
            mail_from="x@x",
            to="t@example.com",
            subject="s",
            html="<p>h</p>",
            transport=transport,
        )


@pytest.mark.asyncio
async def test_send_via_resend_raises_on_429() -> None:
    from news_email.resend_client import send_via_resend

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate"})

    transport = httpx.MockTransport(handler)
    with pytest.raises(RuntimeError, match="rate"):
        await send_via_resend(
            api_key="sk",  # pragma: allowlist secret
            sender_name="x",
            mail_from="x@x",
            to="t@example.com",
            subject="s",
            html="<p>h</p>",
            transport=transport,
        )
```

- [ ] **Step 5.2.2: Run, expect failure; implement**

```python
# services/agents/email/src/news_email/resend_client.py
"""Async httpx wrapper around the Resend HTTP API."""

from __future__ import annotations

from typing import Any

import httpx

RESEND_API_URL = "https://api.resend.com/emails"
RESEND_REQUEST_TIMEOUT = 10.0


async def send_via_resend(
    *,
    api_key: str,
    sender_name: str,
    mail_from: str,
    to: str,
    subject: str,
    html: str,
    text: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """POST to Resend; returns response JSON. Raises RuntimeError on 4xx."""
    payload: dict[str, Any] = {
        "from": f"{sender_name} <{mail_from}>",
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    async with httpx.AsyncClient(
        timeout=RESEND_REQUEST_TIMEOUT, transport=transport
    ) as client:
        resp = await client.post(
            RESEND_API_URL,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
    if resp.status_code == 401:
        raise RuntimeError("Resend authentication failed")
    if resp.status_code == 422:
        raise RuntimeError(f"Resend validation error: {resp.text}")
    if resp.status_code == 429:
        raise RuntimeError("Resend rate limit exceeded")
    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 5.2.3: Pass + commit**

```bash
uv run pytest services/agents/email/src/news_email/tests/unit/test_resend_client.py -v
git add services/agents/email
git commit -m "feat(email): resend_client (httpx async POST + 4xx mapping)"
```

---

### Task 5.3: Jinja2 template + `render.py`

**Files:**
- Create: [services/agents/email/src/news_email/templates/digest.html.j2](services/agents/email/src/news_email/templates/digest.html.j2)
- Create: [services/agents/email/src/news_email/render.py](services/agents/email/src/news_email/render.py)
- Create: [services/agents/email/src/news_email/tests/unit/test_render.py](services/agents/email/src/news_email/tests/unit/test_render.py)

- [ ] **Step 5.3.1: Write the failing tests**

```python
# services/agents/email/src/news_email/tests/unit/test_render.py
from __future__ import annotations

from news_schemas.agent_io import EmailIntroduction
from news_schemas.digest import RankedArticle


def _intro() -> EmailIntroduction:
    return EmailIntroduction(
        greeting="Hi Pat,",
        introduction="Welcome to today's digest. Lots happening in agents land.",
        highlight="The biggest story is the new Agents SDK release.",
        subject_line="AI Daily — agents go GA",
    )


def _ranked() -> list[RankedArticle]:
    return [
        RankedArticle(
            article_id=1,
            score=92,
            title="Agents SDK GA",
            url="https://example.com/1",
            summary="The Agents SDK is generally available.",
            why_ranked="Direct match for your interest in agent orchestration.",
        )
    ]


def test_render_includes_intro_and_articles() -> None:
    from news_email.render import render_digest_html

    html = render_digest_html(_intro(), _ranked(), top_themes=["agents"])
    assert "Hi Pat," in html
    assert "Welcome to today's digest" in html
    assert "Agents SDK GA" in html
    assert "https://example.com/1" in html
    assert "agents" in html


def test_render_handles_zero_articles() -> None:
    from news_email.render import render_digest_html

    html = render_digest_html(_intro(), [], top_themes=[])
    assert "Hi Pat," in html
    assert "<article" not in html
```

- [ ] **Step 5.3.2: Implement template + render**

```html
{# services/agents/email/src/news_email/templates/digest.html.j2 #}
<!doctype html>
<html>
  <body style="font-family: sans-serif; max-width: 640px; margin: 0 auto;">
    <h1>{{ greeting }}</h1>
    <p>{{ introduction }}</p>
    <p><strong>{{ highlight }}</strong></p>
    <hr>
    <h2>Today's top stories</h2>
    {% for article in ranked_articles %}
      <article style="margin-bottom: 1.5em;">
        <h3 style="margin-bottom: 0.25em;">
          <a href="{{ article.url }}">{{ article.title }}</a>
        </h3>
        <p>{{ article.summary }}</p>
        <p><em>Why it matters: {{ article.why_ranked }}</em></p>
        <small>Score: {{ article.score }}/100</small>
      </article>
    {% endfor %}
    <hr>
    <small>Themes: {{ top_themes | join(", ") }}</small>
  </body>
</html>
```

```python
# services/agents/email/src/news_email/render.py
"""Jinja2 renderer for the digest email."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from news_schemas.agent_io import EmailIntroduction
from news_schemas.digest import RankedArticle

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "j2"]),
)


def render_digest_html(
    intro: EmailIntroduction,
    ranked_articles: list[RankedArticle],
    top_themes: list[str],
) -> str:
    template = _env.get_template("digest.html.j2")
    return template.render(
        greeting=intro.greeting,
        introduction=intro.introduction,
        highlight=intro.highlight,
        ranked_articles=[r.model_dump(mode="json") for r in ranked_articles],
        top_themes=top_themes,
    )
```

Note for hatch packaging — add the templates directory to wheel includes. Update `services/agents/email/pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/news_email"]
[tool.hatch.build.targets.wheel.force-include]
"src/news_email/templates" = "news_email/templates"
```

- [ ] **Step 5.3.3: Pass + commit**

```bash
uv run pytest services/agents/email/src/news_email/tests/unit/test_render.py -v
git add services/agents/email
git commit -m "feat(email): digest.html.j2 template + render_digest_html"
```

---

### Task 5.4: `news_email.agent` — `build_agent`

**Files:**
- Create: [services/agents/email/src/news_email/agent.py](services/agents/email/src/news_email/agent.py)
- Create: [services/agents/email/src/news_email/tests/unit/test_agent.py](services/agents/email/src/news_email/tests/unit/test_agent.py)

- [ ] **Step 5.4.1: Test (mirrors digest 3.3.1)**

Assert `output_type is EmailIntroduction`, `name == "EmailAgent"`, and `agent.model == "gpt-5.4-mini"` (string passthrough — no `OpenAIChatCompletionsModel` wrapping).

- [ ] **Step 5.4.2: Implement**

```python
# services/agents/email/src/news_email/agent.py
from __future__ import annotations

from agents import Agent
from news_observability.sanitizer import sanitize_prompt_input
from news_schemas.agent_io import EmailIntroduction


_INSTRUCTIONS = (
    "You are an email composer for a personalised AI news digest. Given the "
    "reader's name, profile, and a ranked list of articles, produce:\n"
    "- greeting: short, friendly, addresses the reader by name\n"
    "- introduction: 2-4 sentences setting up today's digest, written for this "
    "reader's interests\n"
    "- highlight: 1-2 sentences calling out the single most important story\n"
    "- subject_line: punchy, under 120 chars, mentions the top theme\n\n"
    "Tone: warm, smart, never hype. No emojis."
)


def build_agent(*, model: str) -> Agent[EmailIntroduction]:
    return Agent(
        name="EmailAgent",
        instructions=_INSTRUCTIONS,
        model=model,
        output_type=EmailIntroduction,
    )


def build_email_prompt(*, email_name: str, top_themes: list[str], ranked: list[dict]) -> str:
    """Build the user prompt for the email agent.

    Sanitises article *title* and *summary* (scraped third-party text) per the
    AGENTS.md prompt-injection invariant. Hard-block patterns raise
    PromptInjectionError; soft-block patterns are silently redacted. Themes
    and `why_ranked` are LLM-generated upstream so are passed through as-is.
    """
    lines = [
        f"Reader: {email_name}",
        f"Top themes today: {', '.join(top_themes) or 'n/a'}",
        "Ranked articles (highest first):",
    ]
    for r in ranked:
        safe_title = sanitize_prompt_input(r["title"])
        safe_summary = sanitize_prompt_input(r["summary"])
        lines.append(
            f"- [{r['score']}] {safe_title} — {safe_summary} (why: {r['why_ranked']})"
        )
    lines.append("")
    lines.append("Compose greeting, introduction, highlight, and subject_line.")
    return "\n".join(lines)
```

- [ ] **Step 5.4.3: Pass + commit**

```bash
uv run pytest services/agents/email/src/news_email/tests/unit/test_agent.py -v
git add services/agents/email
git commit -m "feat(email): build_agent + build_email_prompt"
```

---

### Task 5.5: `news_email.pipeline` — `send_digest_email`

**Files:**
- Create: [services/agents/email/src/news_email/pipeline.py](services/agents/email/src/news_email/pipeline.py)
- Create: [services/agents/email/src/news_email/tests/unit/test_pipeline.py](services/agents/email/src/news_email/tests/unit/test_pipeline.py)

- [ ] **Step 5.5.1: Write tests covering 4 paths**

1. Idempotency hit (`get_sent_for_digest` returns a row) → no LLM, no Resend; returns existing send_id.
2. Happy path → LLM call, Resend call, `email_sends` row created and marked sent, `digests` flipped to `EMAILED`, audit row.
3. Resend 4xx → `email_sends.mark_failed`, raise.
4. `preview_only=True` → renders HTML, returns it, no Resend call, no DB write.

(Use a `_FakeResender` callable injected as a dependency to avoid real httpx calls.)

```python
# services/agents/email/src/news_email/tests/unit/test_pipeline.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from news_schemas.agent_io import EmailIntroduction
from news_schemas.audit import AuditLogIn
from news_schemas.digest import DigestOut, DigestStatus, RankedArticle
from news_schemas.email_send import EmailSendIn, EmailSendOut, EmailSendStatus
from news_schemas.user_profile import (
    Interests,
    Preferences,
    ReadingTime,
    UserOut,
    UserProfile,
)


@dataclass
class _Usage:
    input_tokens: int = 50
    output_tokens: int = 30
    total_tokens: int = 80
    requests: int = 1


@dataclass
class _Wrapper:
    usage: _Usage


@dataclass
class _FakeResult:
    final_output: EmailIntroduction
    context_wrapper: _Wrapper


def _profile() -> UserProfile:
    return UserProfile(
        background=[], interests=Interests(), preferences=Preferences(),
        goals=[], reading_time=ReadingTime(daily_limit="20m", preferred_article_count="5"),
    )


def _user(uid: UUID) -> UserOut:
    return UserOut(
        id=uid, clerk_user_id="c", email="t@example.com", name="t",
        email_name="Pat", profile=_profile(),
        profile_completed_at=None,
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )


def _digest(did: int, uid: UUID) -> DigestOut:
    return DigestOut(
        id=did, user_id=uid,
        period_start=datetime.now(UTC) - timedelta(hours=24),
        period_end=datetime.now(UTC),
        intro=None,
        ranked_articles=[
            RankedArticle(
                article_id=1, score=80,
                title="T", url="https://x/1", summary="S", why_ranked="ten chars long",
            )
        ],
        top_themes=["agents"], article_count=1,
        status=DigestStatus.GENERATED, error_message=None,
        generated_at=datetime.now(UTC),
    )


def _intro() -> EmailIntroduction:
    return EmailIntroduction(
        greeting="Hi Pat,",
        introduction="Welcome to today's digest, lots happening!",
        highlight="The biggest story is the SDK GA.",
        subject_line="AI Daily — agents go GA",
    )


class _UserRepo:
    def __init__(self, u: UserOut | None) -> None:
        self._u = u

    async def get_by_id(self, uid: UUID) -> UserOut | None:
        return self._u


class _DigestRepo:
    def __init__(self, d: DigestOut | None) -> None:
        self._d = d
        self.status_updates: list[tuple[int, DigestStatus]] = []

    async def get_by_id(self, did: int) -> DigestOut | None:
        return self._d

    async def update_status(
        self, digest_id: int, status: DigestStatus, error: str | None = None
    ) -> DigestOut:
        self.status_updates.append((digest_id, status))
        return self._d  # type: ignore[return-value]


class _EmailRepo:
    def __init__(self, *, sent_existing: EmailSendOut | None = None) -> None:
        self.sent_existing = sent_existing
        self.created: list[EmailSendIn] = []
        self.marked_sent: list[tuple[int, str]] = []
        self.marked_failed: list[tuple[int, str]] = []
        self._next_id = 200

    async def get_sent_for_digest(self, did: int) -> EmailSendOut | None:
        return self.sent_existing

    async def create(self, item: EmailSendIn) -> EmailSendOut:
        self.created.append(item)
        out = EmailSendOut(
            id=self._next_id,
            user_id=item.user_id,
            digest_id=item.digest_id,
            provider=item.provider,
            to_address=item.to_address,
            subject=item.subject,
            status=item.status,
            provider_message_id=item.provider_message_id,
            sent_at=item.sent_at,
            error_message=item.error_message,
        )
        self._next_id += 1
        return out

    async def mark_sent(self, sid: int, provider_message_id: str) -> EmailSendOut:
        self.marked_sent.append((sid, provider_message_id))
        return EmailSendOut(
            id=sid, user_id=uuid4(), digest_id=1,
            provider="resend", to_address="t@example.com",
            subject="s", status=EmailSendStatus.SENT,
            provider_message_id=provider_message_id,
            sent_at=datetime.now(UTC), error_message=None,
        )

    async def mark_failed(self, sid: int, error: str) -> EmailSendOut:
        self.marked_failed.append((sid, error))
        return EmailSendOut(
            id=sid, user_id=uuid4(), digest_id=1,
            provider="resend", to_address="t@example.com",
            subject="s", status=EmailSendStatus.FAILED,
            provider_message_id=None, sent_at=None, error_message=error,
        )


class _AuditRepo:
    def __init__(self) -> None:
        self.entries: list[AuditLogIn] = []

    async def insert(self, e: AuditLogIn) -> None:
        self.entries.append(e)


@pytest.mark.asyncio
async def test_send_digest_skips_when_already_sent() -> None:
    from news_email import pipeline

    uid = uuid4()
    sent_existing = EmailSendOut(
        id=999, user_id=uid, digest_id=1,
        provider="resend", to_address="t@example.com", subject="s",
        status=EmailSendStatus.SENT, provider_message_id="m",
        sent_at=datetime.now(UTC), error_message=None,
    )
    out = await pipeline.send_digest_email(
        digest_id=1,
        user_repo=_UserRepo(_user(uid)),
        digest_repo=_DigestRepo(_digest(1, uid)),
        email_send_repo=_EmailRepo(sent_existing=sent_existing),
        audit_writer=_AuditRepo().insert,
        resend_send=lambda **kw: (_ for _ in ()).throw(AssertionError("called")),
        model="gpt-5.4-mini",
        sender_name="x", mail_from="x@x", mail_to_default="",
    )
    assert out["email_send_id"] == 999
    assert out["skipped"] is True


@pytest.mark.asyncio
async def test_send_digest_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_email import pipeline

    uid = uuid4()
    digest = _digest(1, uid)

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(_intro(), _Wrapper(_Usage()))

    monkeypatch.setattr("news_email.pipeline.Runner.run", _fake_runner_run)

    sends: list[dict[str, Any]] = []

    async def _fake_resend(**kwargs: Any) -> dict[str, Any]:
        sends.append(kwargs)
        return {"id": "msg-1"}

    user_repo = _UserRepo(_user(uid))
    digest_repo = _DigestRepo(digest)
    email_repo = _EmailRepo()
    audit = _AuditRepo()

    out = await pipeline.send_digest_email(
        digest_id=1,
        user_repo=user_repo,
        digest_repo=digest_repo,
        email_send_repo=email_repo,
        audit_writer=audit.insert,
        resend_send=_fake_resend,
        model="gpt-5.4-mini",
        sender_name="AI News", mail_from="hi@news.example", mail_to_default="",
    )
    assert out["skipped"] is False
    assert sends and sends[0]["to"] == "t@example.com"
    assert email_repo.created and email_repo.created[0].subject == "AI Daily — agents go GA"
    assert email_repo.marked_sent == [(200, "msg-1")]
    assert digest_repo.status_updates == [(1, DigestStatus.EMAILED)]
    assert audit.entries


@pytest.mark.asyncio
async def test_send_digest_marks_failed_on_resend_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_email import pipeline

    uid = uuid4()

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(_intro(), _Wrapper(_Usage()))

    monkeypatch.setattr("news_email.pipeline.Runner.run", _fake_runner_run)

    async def _fake_resend(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("Resend rate limit exceeded")

    email_repo = _EmailRepo()
    with pytest.raises(RuntimeError, match="rate limit"):
        await pipeline.send_digest_email(
            digest_id=1,
            user_repo=_UserRepo(_user(uid)),
            digest_repo=_DigestRepo(_digest(1, uid)),
            email_send_repo=email_repo,
            audit_writer=_AuditRepo().insert,
            resend_send=_fake_resend,
            model="gpt-5.4-mini",
            sender_name="x", mail_from="x@x", mail_to_default="",
        )
    assert email_repo.marked_failed and "rate limit" in email_repo.marked_failed[0][1]


@pytest.mark.asyncio
async def test_preview_only_returns_html_no_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_email import pipeline

    uid = uuid4()

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(_intro(), _Wrapper(_Usage()))

    monkeypatch.setattr("news_email.pipeline.Runner.run", _fake_runner_run)

    sent_called = False

    async def _fake_resend(**kwargs: Any) -> dict[str, Any]:
        nonlocal sent_called
        sent_called = True
        return {"id": "x"}

    email_repo = _EmailRepo()
    out = await pipeline.send_digest_email(
        digest_id=1,
        user_repo=_UserRepo(_user(uid)),
        digest_repo=_DigestRepo(_digest(1, uid)),
        email_send_repo=email_repo,
        audit_writer=_AuditRepo().insert,
        resend_send=_fake_resend,
        model="gpt-5.4-mini",
        sender_name="x", mail_from="x@x", mail_to_default="",
        preview_only=True,
    )
    assert "Hi Pat," in out["html"]
    assert sent_called is False
    assert email_repo.created == []
```

- [ ] **Step 5.5.2: Run, expect failure; implement**

```python
# services/agents/email/src/news_email/pipeline.py
"""Email pipeline — compose intro + send via Resend + record."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any, Protocol
from uuid import UUID

from agents import Runner, trace
from news_observability.audit import AuditLogger
from news_observability.costs import extract_usage
from news_observability.logging import get_logger
from news_observability.validators import validate_structured_output
from news_schemas.agent_io import EmailIntroduction
from news_schemas.audit import AgentName, AuditLogIn, DecisionType
from news_schemas.digest import DigestOut, DigestStatus
from news_schemas.email_send import EmailSendIn, EmailSendOut, EmailSendStatus
from news_schemas.user_profile import UserOut

from news_email.agent import build_agent, build_email_prompt
from news_email.render import render_digest_html

_log = get_logger("email_pipeline")
AuditWriter = Callable[[AuditLogIn], Awaitable[None]]
ResendSend = Callable[..., Awaitable[dict[str, Any]]]


class _UserRepo(Protocol):
    async def get_by_id(self, user_id: UUID) -> UserOut | None: ...


class _DigestRepo(Protocol):
    async def get_by_id(self, digest_id: int) -> DigestOut | None: ...
    async def update_status(
        self, digest_id: int, status: DigestStatus, error: str | None = None
    ) -> DigestOut: ...


class _EmailRepo(Protocol):
    async def get_sent_for_digest(self, digest_id: int) -> EmailSendOut | None: ...
    async def create(self, item: EmailSendIn) -> EmailSendOut: ...
    async def mark_sent(self, send_id: int, provider_message_id: str) -> EmailSendOut: ...
    async def mark_failed(self, send_id: int, error: str) -> EmailSendOut: ...


async def send_digest_email(
    *,
    digest_id: int,
    user_repo: _UserRepo,
    digest_repo: _DigestRepo,
    email_send_repo: _EmailRepo,
    audit_writer: AuditWriter,
    resend_send: ResendSend,
    model: str,
    sender_name: str,
    mail_from: str,
    mail_to_default: str,
    preview_only: bool = False,
) -> dict[str, Any]:
    digest = await digest_repo.get_by_id(digest_id)
    if digest is None:
        return {"error": "digest not found", "digest_id": digest_id}

    user = await user_repo.get_by_id(digest.user_id)
    if user is None:
        return {"error": "user not found", "digest_id": digest_id}

    if not preview_only:
        existing = await email_send_repo.get_sent_for_digest(digest_id)
        if existing:
            return {"email_send_id": existing.id, "skipped": True}

    agent = build_agent(model=model)
    ranked_payload = [
        {
            "title": r.title,
            "summary": r.summary,
            "why_ranked": r.why_ranked,
            "score": r.score,
        }
        for r in digest.ranked_articles
    ]
    prompt = build_email_prompt(
        email_name=user.email_name,
        top_themes=digest.top_themes,
        ranked=ranked_payload,
    )

    t0 = perf_counter()
    with trace(f"email.digest.{digest_id}"):
        result = await Runner.run(agent, input=prompt)
    elapsed_ms = int((perf_counter() - t0) * 1000)

    intro = validate_structured_output(EmailIntroduction, result.final_output)
    usage = extract_usage(result, model=model)
    html = render_digest_html(intro, digest.ranked_articles, digest.top_themes)

    if preview_only:
        return {
            "html": html,
            "subject": intro.subject_line,
            "model": usage.model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        }

    to_address = mail_to_default or user.email
    send_row = await email_send_repo.create(
        EmailSendIn(
            user_id=user.id,
            digest_id=digest_id,
            to_address=to_address,
            subject=intro.subject_line,
            status=EmailSendStatus.PENDING,
        )
    )

    try:
        resp = await resend_send(
            to=to_address,
            subject=intro.subject_line,
            html=html,
            sender_name=sender_name,
            mail_from=mail_from,
        )
    except Exception as exc:
        await email_send_repo.mark_failed(send_row.id, error=str(exc))
        raise

    provider_id = str(resp.get("id", ""))
    await email_send_repo.mark_sent(send_row.id, provider_message_id=provider_id)
    await digest_repo.update_status(digest_id, DigestStatus.EMAILED)

    audit = AuditLogger(audit_writer)
    await audit.log_decision(
        agent_name=AgentName.EMAIL,
        user_id=user.id,
        decision_type=DecisionType.INTRO,
        input_text=f"digest {digest_id} for {user.email_name}",
        output_text=intro.introduction,
        metadata={
            "digest_id": digest_id,
            "email_send_id": send_row.id,
            "provider_message_id": provider_id,
            "subject": intro.subject_line,
            "model": usage.model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "requests": usage.requests,
            "estimated_cost_usd": usage.estimated_cost_usd,
            "duration_ms": elapsed_ms,
        },
    )

    return {
        "email_send_id": send_row.id,
        "provider_message_id": provider_id,
        "skipped": False,
    }
```

The `resend_send` argument is supplied at the call site (CLI / lambda_handler) as a thin wrapper around `resend_client.send_via_resend` that closes over the api key. Pipeline takes only the parameters that vary per call.

- [ ] **Step 5.5.3: Pass + commit**

```bash
uv run pytest services/agents/email/src/news_email/tests/unit/test_pipeline.py -v
uv run mypy services/agents/email
git add services/agents/email
git commit -m "feat(email): send_digest_email pipeline (compose + send + record + idempotency + preview)"
```

---

### Task 5.6: Email CLI + lambda_handler

- [ ] **Step 5.6.1: Implement `cli.py`**

```python
# services/agents/email/src/news_email/cli.py
from __future__ import annotations

import asyncio
import sys
from functools import partial

import typer
from news_db.engine import get_session
from news_db.repositories.audit_log_repo import AuditLogRepository
from news_db.repositories.digest_repo import DigestRepository
from news_db.repositories.email_send_repo import EmailSendRepository
from news_db.repositories.user_repo import UserRepository
from news_observability.logging import setup_logging

from news_email.pipeline import send_digest_email
from news_email.resend_client import send_via_resend
from news_email.settings import EmailSettings

app = typer.Typer(no_args_is_help=True, help="Email agent CLI")


def _resend_send_factory(api_key: str):
    async def _send(**kwargs):
        return await send_via_resend(api_key=api_key, **kwargs)
    return _send


@app.command()
def send(digest_id: int) -> None:
    """Compose + Resend-send the email for a digest."""

    async def _run() -> int:
        setup_logging()
        s = EmailSettings()
        async with get_session() as session:
            out = await send_digest_email(
                digest_id=digest_id,
                user_repo=UserRepository(session),
                digest_repo=DigestRepository(session),
                email_send_repo=EmailSendRepository(session),
                audit_writer=AuditLogRepository(session).insert,
                resend_send=_resend_send_factory(s.resend.api_key),
                model=s.openai.model,
                sender_name=s.mail.sender_name,
                mail_from=s.mail.mail_from,
                mail_to_default=s.mail.mail_to_default,
            )
        typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))


@app.command()
def preview(digest_id: int) -> None:
    """Render the digest HTML to stdout (no LLM unless needed; no send)."""

    async def _run() -> int:
        setup_logging()
        s = EmailSettings()
        async with get_session() as session:
            out = await send_digest_email(
                digest_id=digest_id,
                user_repo=UserRepository(session),
                digest_repo=DigestRepository(session),
                email_send_repo=EmailSendRepository(session),
                audit_writer=AuditLogRepository(session).insert,
                resend_send=_resend_send_factory(s.resend.api_key),
                model=s.openai.model,
                sender_name=s.mail.sender_name,
                mail_from=s.mail.mail_from,
                mail_to_default=s.mail.mail_to_default,
                preview_only=True,
            )
        if "html" in out:
            typer.echo(out["html"])
        else:
            typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))
```

`__main__.py`: `from news_email.cli import app; app()`

- [ ] **Step 5.6.2: Implement `lambda_handler.py`**

```python
# services/agents/email/lambda_handler.py
from __future__ import annotations

import asyncio
import os
from typing import Any

from news_config.lambda_settings import load_settings_from_ssm

load_settings_from_ssm(prefix=os.environ.get("SSM_PARAM_PREFIX", "/news-aggregator/dev"))

from news_db.engine import get_session  # noqa: E402
from news_db.repositories.audit_log_repo import AuditLogRepository  # noqa: E402
from news_db.repositories.digest_repo import DigestRepository  # noqa: E402
from news_db.repositories.email_send_repo import EmailSendRepository  # noqa: E402
from news_db.repositories.user_repo import UserRepository  # noqa: E402
from news_observability.logging import setup_logging  # noqa: E402
from news_observability.tracing import configure_tracing  # noqa: E402

from news_email.pipeline import send_digest_email  # noqa: E402
from news_email.resend_client import send_via_resend  # noqa: E402
from news_email.settings import EmailSettings  # noqa: E402

setup_logging()
configure_tracing(enable_langfuse=True)


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    digest_id = int(event["digest_id"])
    return asyncio.run(_run(digest_id))


async def _run(digest_id: int) -> dict[str, Any]:
    s = EmailSettings()

    async def _send(**kwargs: Any) -> dict[str, Any]:
        return await send_via_resend(api_key=s.resend.api_key, **kwargs)

    async with get_session() as session:
        return await send_digest_email(
            digest_id=digest_id,
            user_repo=UserRepository(session),
            digest_repo=DigestRepository(session),
            email_send_repo=EmailSendRepository(session),
            audit_writer=AuditLogRepository(session).insert,
            resend_send=_send,
            model=s.openai.model,
            sender_name=s.mail.sender_name,
            mail_from=s.mail.mail_from,
            mail_to_default=s.mail.mail_to_default,
        )
```

- [ ] **Step 5.6.3: Run all email tests, expect pass; commit**

```bash
uv run pytest services/agents/email -v
git add services/agents/email
git commit -m "feat(email): Typer CLI (send + preview) + lambda_handler"
```

---

### Task 5.7: Email `package_docker.py`

- [ ] **Step 5.7.1: Adapt the digest version**

Same template; constants: `PACKAGE_NAME = "news_email"`, agent dir = `email`. The `force-include` for `templates/` ensures the Jinja file is in the wheel; `cp -r .../news_email /pkg/` already copies the templates folder since it lives under the package source.

- [ ] **Step 5.7.2: Smoke build + commit**

```bash
uv run python services/agents/email/package_docker.py
ls -lh services/agents/email/dist/news_email.zip
git add services/agents/email/package_docker.py
git commit -m "build(email): package_docker.py"
```

---

### Task 5.8: Phase 5 verification

- [ ] **Step 5.8.1: Run full check**

```bash
uv run ruff check
uv run mypy packages services/agents/digest services/agents/editor services/agents/email
uv run pytest -q
```

All green. Phase 5 done.

---

## Phase 6 — Per-agent Terraform modules

Three modules under `infra/{digest,editor,email}/`. Each one consumes the bootstrap remote-state output for the artifacts bucket and exposes a `function_name` + `function_arn` output. Run module 1 (digest) end-to-end first; modules 2 + 3 are copy-and-tweak.

### Task 6.1: `infra/digest/`

**Files:**
- Create: [infra/digest/main.tf](infra/digest/main.tf)
- Create: [infra/digest/variables.tf](infra/digest/variables.tf)
- Create: [infra/digest/outputs.tf](infra/digest/outputs.tf)
- Create: [infra/digest/data.tf](infra/digest/data.tf)
- Create: [infra/digest/backend.tf](infra/digest/backend.tf)
- Create: [infra/digest/terraform.tfvars.example](infra/digest/terraform.tfvars.example)

- [ ] **Step 6.1.1: Author `backend.tf`**

```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.42.0"
    }
  }

  backend "s3" {
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}
```

- [ ] **Step 6.1.2: Author `data.tf`**

```hcl
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "terraform_remote_state" "bootstrap" {
  backend = "s3"
  config = {
    bucket  = "news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}"
    key     = "bootstrap/terraform.tfstate"
    region  = "us-east-1"
    profile = var.aws_profile
  }
}
```

- [ ] **Step 6.1.3: Author `variables.tf`**

```hcl
variable "aws_region" { type = string; default = "us-east-1" }
variable "aws_profile" { type = string; default = "aiengineer" }

variable "zip_s3_key" {
  description = "S3 key inside the artifact bucket (e.g. digest/<sha>.zip). Set by deploy.py."
  type        = string
}

variable "zip_sha256" {
  description = "Base64-encoded SHA256 of the zip — Lambda's source_code_hash."
  type        = string
}

variable "memory_size" { type = number; default = 1024 }
variable "timeout"     { type = number; default = 60 }

variable "log_retention_days" { type = number; default = 14 }

variable "openai_model" {
  type    = string
  default = "gpt-5.4-mini"
}
```

- [ ] **Step 6.1.4: Author `main.tf`**

```hcl
locals {
  function_name = "news-digest-${terraform.workspace}"
  ssm_prefix    = "/news-aggregator/${terraform.workspace}"
}

resource "aws_iam_role" "lambda_exec" {
  name = local.function_name
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = { Project = "news-aggregator", Module = "digest" }
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "ssm_read" {
  role = aws_iam_role.lambda_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath",
        ]
        Resource = "arn:aws:ssm:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}/*"
      },
      {
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = "arn:aws:kms:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:alias/aws/ssm"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "this" {
  function_name    = local.function_name
  role             = aws_iam_role.lambda_exec.arn
  package_type     = "Zip"
  runtime          = "python3.12"
  handler          = "lambda_handler.handler"
  s3_bucket        = data.terraform_remote_state.bootstrap.outputs.lambda_artifacts_bucket
  s3_key           = var.zip_s3_key
  source_code_hash = var.zip_sha256
  timeout          = var.timeout
  memory_size      = var.memory_size
  architectures    = ["x86_64"]

  environment {
    variables = {
      ENV              = terraform.workspace
      LOG_LEVEL        = "INFO"
      LOG_JSON         = "true"
      OPENAI_MODEL     = var.openai_model
      SSM_PARAM_PREFIX = local.ssm_prefix
      LANGFUSE_HOST    = "https://cloud.langfuse.com"
    }
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.lambda.name
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.ssm_read,
    aws_cloudwatch_log_group.lambda,
  ]

  tags = { Project = "news-aggregator", Module = "digest" }
}
```

- [ ] **Step 6.1.5: Author `outputs.tf`**

```hcl
output "function_name" { value = aws_lambda_function.this.function_name }
output "function_arn"  { value = aws_lambda_function.this.arn }
output "log_group_name" { value = aws_cloudwatch_log_group.lambda.name }
```

- [ ] **Step 6.1.6: Author `terraform.tfvars.example`**

```hcl
zip_s3_key  = "digest/<git-sha>.zip"
zip_sha256  = "<base64-sha256>"
```

- [ ] **Step 6.1.7: `terraform init` (don't apply yet — needs zip + deploy.py from Phase 7)**

```bash
cd infra/digest
terraform init \
  -backend-config="bucket=news-aggregator-tf-state-$(aws sts get-caller-identity --profile aiengineer --query Account --output text)" \
  -backend-config="key=digest/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="profile=aiengineer"
cd ../..
```

- [ ] **Step 6.1.8: Commit**

```bash
git add infra/digest
git commit -m "infra(digest): Lambda module (zip + S3 + IAM + log group + SSM read)"
```

---

### Task 6.2: `infra/editor/`

- [ ] **Step 6.2.1: Copy `infra/digest/*` to `infra/editor/`**

```bash
cp -r infra/digest infra/editor
```

- [ ] **Step 6.2.2: Edit module overrides**

In `infra/editor/main.tf`:
- `local.function_name = "news-editor-${terraform.workspace}"`
- replace `Module = "digest"` with `Module = "editor"` (two occurrences)

In `infra/editor/variables.tf` (override defaults per spec §6.3):
- `variable "memory_size"  { type = number; default = 2048 }`
- `variable "timeout"      { type = number; default = 300 }`

`outputs.tf` and `data.tf` remain identical.

- [ ] **Step 6.2.3: `terraform init` for editor**

```bash
cd infra/editor
terraform init \
  -backend-config="bucket=news-aggregator-tf-state-$(aws sts get-caller-identity --profile aiengineer --query Account --output text)" \
  -backend-config="key=editor/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="profile=aiengineer"
cd ../..
```

- [ ] **Step 6.2.4: Commit**

```bash
git add infra/editor
git commit -m "infra(editor): Lambda module (timeout=300, memory=2048)"
```

---

### Task 6.3: `infra/email/`

- [ ] **Step 6.3.1: Copy `infra/digest/` to `infra/email/`**

```bash
cp -r infra/digest infra/email
```

- [ ] **Step 6.3.2: Edit `infra/email/main.tf`**

- `local.function_name = "news-email-${terraform.workspace}"`
- `Module = "email"` everywhere
- timeout default unchanged (60); memory default unchanged (1024)
- Add three extra env vars to `aws_lambda_function.this.environment.variables`:

```hcl
      MAIL_FROM        = var.mail_from
      SENDER_NAME      = var.sender_name
      MAIL_TO_DEFAULT  = var.mail_to_default
```

- [ ] **Step 6.3.3: Edit `infra/email/variables.tf`**

Add at the bottom:

```hcl
variable "mail_from" {
  description = "Resend-verified From: address"
  type        = string
}

variable "sender_name" {
  type    = string
  default = "AI News Digest"
}

variable "mail_to_default" {
  description = "Override To: for testing (empty in prod)"
  type        = string
  default     = ""
}
```

Override defaults: `timeout = 120` (vs 60 elsewhere — Resend can be slow):

```hcl
variable "timeout" { type = number; default = 120 }
```

- [ ] **Step 6.3.4: `terraform init` for email**

```bash
cd infra/email
terraform init \
  -backend-config="bucket=news-aggregator-tf-state-$(aws sts get-caller-identity --profile aiengineer --query Account --output text)" \
  -backend-config="key=email/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="profile=aiengineer"
cd ../..
```

- [ ] **Step 6.3.5: Commit**

```bash
git add infra/email
git commit -m "infra(email): Lambda module (mail_from + sender_name + mail_to_default + timeout=120)"
```

---

## Phase 7 — Per-agent `deploy.py`

Each `deploy.py` is a small wrapper: build → upload → terraform apply. Copy/adapt the existing scraper one but for Lambda zips.

### Task 7.1: `services/agents/digest/deploy.py`

- [ ] **Step 7.1.1: Implement**

```python
# services/agents/digest/deploy.py
"""Build, upload, and deploy the digest Lambda.

Modes:
  build   — package_docker.py → S3 upload
  deploy  — build + terraform apply

Examples:
  uv run python services/agents/digest/deploy.py --mode build
  uv run python services/agents/digest/deploy.py --mode deploy --env dev
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import boto3

AGENT_DIR = Path(__file__).resolve().parent
PACKAGE = "news_digest"
TF_DIR = AGENT_DIR.parents[2] / "infra" / "digest"


def _profile() -> str:
    return os.environ.get("AWS_PROFILE", "aiengineer")


def _session() -> boto3.Session:
    return boto3.Session(profile_name=_profile())


def _account_id(s: boto3.Session) -> str:
    return s.client("sts").get_caller_identity()["Account"]  # type: ignore[no-any-return]


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _bucket(s: boto3.Session) -> str:
    return f"news-aggregator-lambda-artifacts-{_account_id(s)}"


def _zip_path() -> Path:
    return AGENT_DIR / "dist" / f"{PACKAGE}.zip"


def _build_zip() -> Path:
    subprocess.run(
        ["uv", "run", "python", str(AGENT_DIR / "package_docker.py")],
        check=True,
    )
    z = _zip_path()
    if not z.exists():
        raise RuntimeError(f"build did not produce {z}")
    return z


def _b64_sha256(path: Path) -> str:
    h = hashlib.sha256(path.read_bytes()).digest()
    return base64.b64encode(h).decode()


def _upload(s: boto3.Session, sha: str, zip_path: Path) -> str:
    key = f"digest/{sha}.zip"
    s.client("s3").upload_file(str(zip_path), _bucket(s), key)
    print(f"uploaded s3://{_bucket(s)}/{key}")
    return key


def cmd_build() -> int:
    s = _session()
    sha = _git_sha()
    zip_path = _build_zip()
    _upload(s, sha, zip_path)
    print(f"sha256(zip) = {_b64_sha256(zip_path)}")
    return 0


def cmd_deploy(env: str) -> int:
    s = _session()
    sha = _git_sha()
    zip_path = _build_zip()
    key = _upload(s, sha, zip_path)
    sha256 = _b64_sha256(zip_path)

    tf_env = {**os.environ, "AWS_PROFILE": _profile()}
    try:
        subprocess.run(
            ["terraform", "workspace", "select", env],
            cwd=TF_DIR, check=True, env=tf_env,
        )
    except subprocess.CalledProcessError:
        subprocess.run(
            ["terraform", "workspace", "new", env],
            cwd=TF_DIR, check=True, env=tf_env,
        )

    subprocess.run(
        [
            "terraform", "apply", "-auto-approve",
            f"-var=zip_s3_key={key}",
            f"-var=zip_sha256={sha256}",
        ],
        cwd=TF_DIR, check=True, env=tf_env,
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["build", "deploy"], required=True)
    p.add_argument("--env", default="dev")
    args = p.parse_args()
    return cmd_build() if args.mode == "build" else cmd_deploy(args.env)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7.1.2: Smoke test build mode**

```bash
uv run python services/agents/digest/deploy.py --mode build
```

Expected: zip built, uploaded to `s3://news-aggregator-lambda-artifacts-<acct>/digest/<sha>.zip`.

- [ ] **Step 7.1.3: Deploy to dev**

```bash
uv run python services/agents/digest/deploy.py --mode deploy --env dev
```

Expected: terraform applies, Lambda `news-digest-dev` exists.

- [ ] **Step 7.1.4: Smoke-test the Lambda**

You'll need an existing article ID with `summary IS NULL`. Pick one via:

```bash
make scraper-test-runs        # find a recent run
# OR query the DB directly:
uv run python -c "import asyncio; from news_db.engine import get_session; from news_db.repositories.article_repo import ArticleRepository; \
  async def m():\
    async with get_session() as s: print([(a.id, a.title) for a in await ArticleRepository(s).get_unsummarized(hours=72, limit=5)]); \
  asyncio.run(m())"
```

Pick an article id, then:

```bash
aws lambda invoke --function-name news-digest-dev \
  --payload '{"article_id": <ID>}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/out.json --profile aiengineer
cat /tmp/out.json | jq
```

Expected: `{"article_id": <ID>, "summary": "...", "skipped": false, ...}`. Verify with:

```bash
uv run python -c "import asyncio; from news_db.engine import get_session; from news_db.repositories.article_repo import ArticleRepository; \
  async def m():\
    async with get_session() as s: a = await ArticleRepository(s).get_by_id(<ID>); print(a.summary); \
  asyncio.run(m())"
```

- [ ] **Step 7.1.5: Commit**

```bash
git add services/agents/digest/deploy.py
git commit -m "build(digest): deploy.py (build → S3 → terraform apply)"
```

---

### Task 7.2: `services/agents/editor/deploy.py`

- [ ] **Step 7.2.1: Copy + adapt the digest version**

```bash
cp services/agents/digest/deploy.py services/agents/editor/deploy.py
```

In `services/agents/editor/deploy.py`, change:
- `PACKAGE = "news_editor"`
- `TF_DIR = AGENT_DIR.parents[2] / "infra" / "editor"`
- S3 prefix: `key = f"editor/{sha}.zip"` (in `_upload`)

- [ ] **Step 7.2.2: Smoke build + deploy + invoke**

```bash
uv run python services/agents/editor/deploy.py --mode deploy --env dev
```

Then invoke (need a seed user; if not seeded, run `make seed` first):

```bash
USER_ID=$(uv run python -c "import asyncio; from news_db.engine import get_session; from news_db.repositories.user_repo import UserRepository; from sqlalchemy import select; from news_db.models.user import User; \
  async def m():\
    async with get_session() as s: rows = (await s.execute(select(User).limit(1))).scalars().all(); print(rows[0].id); \
  asyncio.run(m())")

aws lambda invoke --function-name news-editor-dev \
  --payload "{\"user_id\": \"$USER_ID\", \"lookback_hours\": 24}" \
  --cli-binary-format raw-in-base64-out \
  /tmp/out.json --profile aiengineer
cat /tmp/out.json | jq
```

Expected: `{"digest_id": ..., "status": "generated", "ranked": N}` where N ≤ 10.

- [ ] **Step 7.2.3: Commit**

```bash
git add services/agents/editor/deploy.py
git commit -m "build(editor): deploy.py"
```

---

### Task 7.3: `services/agents/email/deploy.py`

- [ ] **Step 7.3.1: Copy + adapt**

```bash
cp services/agents/digest/deploy.py services/agents/email/deploy.py
```

Edits in `services/agents/email/deploy.py`:
- `PACKAGE = "news_email"`
- `TF_DIR = AGENT_DIR.parents[2] / "infra" / "email"`
- `key = f"email/{sha}.zip"`
- In `cmd_deploy`, append `-var=mail_from=$MAIL_FROM`, optionally `-var=mail_to_default=$MAIL_TO_DEFAULT`. Use env vars (read at deploy time) so secrets don't live in the repo:

```python
mail_from = os.environ.get("MAIL_FROM")
if not mail_from:
    raise RuntimeError("MAIL_FROM env var required for email deploy")
extra_vars = [f"-var=mail_from={mail_from}"]
if os.environ.get("MAIL_TO_DEFAULT"):
    extra_vars.append(f"-var=mail_to_default={os.environ['MAIL_TO_DEFAULT']}")
# ...
subprocess.run(
    [
        "terraform", "apply", "-auto-approve",
        f"-var=zip_s3_key={key}",
        f"-var=zip_sha256={sha256}",
        *extra_vars,
    ],
    cwd=TF_DIR, check=True, env=tf_env,
)
```

- [ ] **Step 7.3.2: Smoke build + deploy + preview-invoke**

Preview avoids actually emailing during smoke:

```bash
MAIL_FROM=hi@yourdomain.com MAIL_TO_DEFAULT=you@yourdomain.com \
  uv run python services/agents/email/deploy.py --mode deploy --env dev

# Find a digest ID from the editor invocation in 7.2.2:
DIGEST_ID=<from previous step>

aws lambda invoke --function-name news-email-dev \
  --payload "{\"digest_id\": $DIGEST_ID}" \
  --cli-binary-format raw-in-base64-out \
  /tmp/out.json --profile aiengineer
cat /tmp/out.json | jq
```

Check your inbox for the email. Verify rows in DB:

```bash
uv run python -c "import asyncio; from news_db.engine import get_session; \
  async def m():\
    async with get_session() as s: rows = await s.execute('select id, status, subject, sent_at from email_sends order by id desc limit 3'); print(rows.all()); \
  asyncio.run(m())"
```

- [ ] **Step 7.3.3: Commit**

```bash
git add services/agents/email/deploy.py
git commit -m "build(email): deploy.py (mail_from from env)"
```

---

## Phase 8 — Makefile + docs + tag

### Task 8.1: Makefile additions

- [ ] **Step 8.1.1: Append `agents-*` targets to `Makefile`**

```makefile
# ---------- agents (#2) ----------

.PHONY: agents-digest agents-editor agents-email agents-preview \
        digest-deploy-build digest-deploy digest-invoke \
        editor-deploy-build editor-deploy editor-invoke \
        email-deploy-build email-deploy email-invoke \
        agents-logs agents-logs-follow tag-agents

agents-digest:                ## summarise one article (ARTICLE_ID=...) — local CLI
	@test -n "$(ARTICLE_ID)" || (echo "ARTICLE_ID required" && exit 1)
	uv run python -m news_digest summarize $(ARTICLE_ID)

agents-digest-sweep:          ## summarise all unsummarised articles  [LOOKBACK=24]
	uv run python -m news_digest sweep --hours $${LOOKBACK:-24}

agents-editor:                ## rank for user (USER_ID=... LOOKBACK=24)
	@test -n "$(USER_ID)" || (echo "USER_ID required" && exit 1)
	uv run python -m news_editor rank $(USER_ID) --hours $${LOOKBACK:-24}

agents-email:                 ## send email for digest (DIGEST_ID=...)
	@test -n "$(DIGEST_ID)" || (echo "DIGEST_ID required" && exit 1)
	uv run python -m news_email send $(DIGEST_ID)

agents-preview:               ## preview email HTML (DIGEST_ID=...) → stdout
	@test -n "$(DIGEST_ID)" || (echo "DIGEST_ID required" && exit 1)
	uv run python -m news_email preview $(DIGEST_ID)

# ---- per-agent deploy ----

digest-deploy-build:          ## build + s3 upload (digest)
	uv run python services/agents/digest/deploy.py --mode build

digest-deploy:                ## build + terraform apply (digest)
	uv run python services/agents/digest/deploy.py --mode deploy --env dev

editor-deploy-build:
	uv run python services/agents/editor/deploy.py --mode build
editor-deploy:
	uv run python services/agents/editor/deploy.py --mode deploy --env dev

email-deploy-build:
	uv run python services/agents/email/deploy.py --mode build
email-deploy:                 ## requires MAIL_FROM (and optionally MAIL_TO_DEFAULT)
	@test -n "$(MAIL_FROM)" || (echo "MAIL_FROM required" && exit 1)
	uv run python services/agents/email/deploy.py --mode deploy --env dev

# ---- live invoke ----

digest-invoke:                ## aws lambda invoke (ARTICLE_ID=...)
	@test -n "$(ARTICLE_ID)" || (echo "ARTICLE_ID required" && exit 1)
	@aws lambda invoke --function-name news-digest-dev \
	  --payload '{"article_id":$(ARTICLE_ID)}' \
	  --cli-binary-format raw-in-base64-out \
	  /tmp/digest-out.json --profile aiengineer && jq . /tmp/digest-out.json

editor-invoke:                ## aws lambda invoke (USER_ID=...)
	@test -n "$(USER_ID)" || (echo "USER_ID required" && exit 1)
	@aws lambda invoke --function-name news-editor-dev \
	  --payload '{"user_id":"$(USER_ID)","lookback_hours":24}' \
	  --cli-binary-format raw-in-base64-out \
	  /tmp/editor-out.json --profile aiengineer && jq . /tmp/editor-out.json

email-invoke:                 ## aws lambda invoke (DIGEST_ID=...)
	@test -n "$(DIGEST_ID)" || (echo "DIGEST_ID required" && exit 1)
	@aws lambda invoke --function-name news-email-dev \
	  --payload '{"digest_id":$(DIGEST_ID)}' \
	  --cli-binary-format raw-in-base64-out \
	  /tmp/email-out.json --profile aiengineer && jq . /tmp/email-out.json

# ---- logs ----

agents-logs:                  ## tail one agent's logs (AGENT=digest|editor|email SINCE=10m)
	@test -n "$(AGENT)" || (echo "AGENT required: digest|editor|email" && exit 1)
	aws logs tail /aws/lambda/news-$(AGENT)-dev --since $${SINCE:-10m} --profile aiengineer

agents-logs-follow:
	@test -n "$(AGENT)" || (echo "AGENT required" && exit 1)
	aws logs tail /aws/lambda/news-$(AGENT)-dev --follow --profile aiengineer

# ---- tag ----

tag-agents:                   ## tag sub-project #2
	git tag -f -a agents-v0.3.0 -m "Sub-project #2 Agents"
	@echo "Push with: git push origin agents-v0.3.0"
```

Update the `.PHONY` line at the top of the file too if needed (or rely on the dedicated PHONY block here).

- [ ] **Step 8.1.2: Verify `make help` lists the new targets**

```bash
make help | grep -E "agents|digest|editor|email"
```

- [ ] **Step 8.1.3: Commit**

```bash
git add Makefile
git commit -m "build(make): add agents-* targets (local + deploy + invoke + logs)"
```

---

### Task 8.2: Update `infra/README.md`

- [ ] **Step 8.2.1: Document the agent module lifecycle**

Append a section "Sub-project #2 — agents" to `infra/README.md` covering:

- One-time bootstrap-extension apply that adds the artifact bucket
- Per-agent `terraform init` invocation (one per `infra/{digest,editor,email}/`)
- Deploy via `make digest-deploy` / `make editor-deploy` / `make email-deploy MAIL_FROM=...`
- How to roll back: `terraform apply -var=zip_s3_key=<previous-key> -var=zip_sha256=<previous-sha256>`
- IAM scope: each Lambda gets its own role with read access to `arn:aws:ssm:...:parameter/news-aggregator/<env>/*`
- Cost: artifact bucket lifecycle expires noncurrent versions after 90 days; ~50 KB-USD/month for state
- Failure modes: `make agents-logs AGENT=digest SINCE=10m` is the first stop

Keep it short — under 50 lines.

- [ ] **Step 8.2.2: Commit**

```bash
git add infra/README.md
git commit -m "docs(infra): document sub-project #2 agent lifecycle"
```

---

### Task 8.3: AGENTS.md refresh

- [ ] **Step 8.3.1: Update `AGENTS.md` "Sub-project decomposition" section**

Update the table to mark sub-project #2 as "Done", note `agents-v0.3.0` tag, and link the spec + plan paths. Add a "Sub-project #2 — Agents" section with a 1-paragraph description that mirrors what we did for #1: three Lambdas, zip-on-S3, package_docker.py, deploy.py per agent, per-agent Terraform module under `infra/`. Note the new Foundation additions: `news_schemas.agent_io`, `news_config.lambda_settings`, `news_config.MailSettings`, three new article-repo methods, `EmailSendRepository.get_sent_for_digest`.

- [ ] **Step 8.3.2: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): refresh AGENTS.md for sub-project #2"
```

---

### Task 8.4: Final verification

- [ ] **Step 8.4.1: Run the full check (CI-equivalent)**

```bash
make check
```

Expected: ruff check + format check, mypy on packages, pytest all green.

- [ ] **Step 8.4.2: Live-trigger end-to-end happy path**

```bash
# 1. Trigger ingestion (sub-project #1)
make scraper-test-ingest LOOKBACK=24

# 2. Sweep digest agent over the new articles (locally — fast iteration)
make agents-digest-sweep LOOKBACK=24

# 3. Find the seed user
USER_ID=$(uv run python scripts/seed_user.py --print-id 2>/dev/null || \
  uv run python -c "import asyncio; from news_db.engine import get_session; from sqlalchemy import select; from news_db.models.user import User; \
    async def m():\
      async with get_session() as s: u=(await s.execute(select(User).limit(1))).scalar_one(); print(u.id); \
    asyncio.run(m())")

# 4. Editor — invoke Lambda live
make editor-invoke USER_ID=$USER_ID
# capture digest_id from output

# 5. Email — preview locally first (no send)
make agents-preview DIGEST_ID=<from-step-4>

# 6. Email — invoke Lambda live (real Resend send)
MAIL_TO_DEFAULT=you@yourdomain.com make email-invoke DIGEST_ID=<from-step-4>
```

Verify:
- Articles get summaries (`select count(*) from articles where summary is not null;`)
- A `digests` row was written with `status='emailed'`
- An `email_sends` row exists with `status='sent'` and a `provider_message_id`
- Audit logs show three new entries (`digest_agent`, `editor_agent`, `email_agent`)
- The email arrived in your inbox

- [ ] **Step 8.4.3: Tag the release**

```bash
make tag-agents
git push origin agents-v0.3.0
```

- [ ] **Step 8.4.4: Final commit (any housekeeping changes)**

```bash
git status
# if anything tracked is dirty
git commit -m "chore: tidy up after sub-project #2"
```

---

## Self-Review

After writing this plan:

**Spec coverage:** Every section of the spec maps to a phase:
- §3 Architecture → Phases 3 + 4 + 5
- §4 Repo layout → Tasks 3.1, 4.1, 5.1, 6.x
- §5 Per-agent details → Tasks 3.3-3.6, 4.3-4.5, 5.4-5.6
- §6 Lambda packaging + Terraform → Tasks 3.7, 4.6, 5.7, 6.x, 7.x
- §6.4 SSM secrets → Task 3.6 (`load_settings_from_ssm`)
- §6.5 Bootstrap extension → Phase 2
- §7 Local dev + Make targets → Tasks 8.1
- §8 Audit logging → embedded in 3.4, 4.4, 5.5 pipeline implementations
- §9 Error handling → covered by tests in pipeline tasks
- §10 Cost guardrails → audit metadata captures cost; verified in tests
- §13 Sub-project deps → Phase 1 adds new repo methods + schemas only
- §14 Phasing → mapped 1:1

**Placeholder scan:** No "TBD" / "TODO" / "implement later" / "similar to" entries. Every code step has full code. Every test step has full assertions.

**Type consistency:** `summarize_article` (digest), `rank_for_user` (editor), `send_digest_email` (email) signatures consistent across pipeline definition and CLI/handler call sites. `AgentName.DIGEST` / `EDITOR` / `EMAIL` (matches `audit.py` enum). `DigestStatus.GENERATED` / `EMAILED` / `FAILED` exist (verified). `EmailSendStatus.PENDING` / `SENT` / `FAILED` exist (verified). `RankedArticle` fields used in pipeline match the schema (`article_id`, `score`, `title`, `url`, `summary`, `why_ranked`).

**Risks captured:** Model passed as a plain string — SDK chooses the backend (currently Responses API by default), asserted with `test_build_agent_passes_model_string_through`. HttpUrl/EmailStr forbidden in LLM-side schemas — only plain `str` is used. Templates folder force-included in hatch wheel. `package_docker.py` Dockerfile copies first-party workspace packages explicitly because they aren't on PyPI.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-26-agents-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
