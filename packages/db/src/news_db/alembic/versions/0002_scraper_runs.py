"""scraper_runs — ingestion run bookkeeping

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scraper_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("trigger", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="running"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lookback_hours", sa.Integer, nullable=False),
        sa.Column("pipelines_requested", postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column(
            "stats",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.CheckConstraint(
            "status in ('running','success','partial','failed')",
            name="scraper_runs_status_check",
        ),
    )
    op.create_index("ix_scraper_runs_started", "scraper_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_scraper_runs_started", table_name="scraper_runs")
    op.drop_table("scraper_runs")
