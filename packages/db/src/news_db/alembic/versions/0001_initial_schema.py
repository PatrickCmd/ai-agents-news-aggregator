"""initial schema — articles, users, digests, email_sends, audit_logs

Revision ID: 0001
Revises:
Create Date: 2026-04-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgcrypto gives us gen_random_uuid()
    op.execute("create extension if not exists pgcrypto")

    # updated_at trigger function
    op.execute(
        """
        create or replace function set_updated_at()
        returns trigger as $$
        begin
            new.updated_at = now();
            return new;
        end;
        $$ language plpgsql
        """
    )

    # users
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("clerk_user_id", sa.String, nullable=False),
        sa.Column("email", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("email_name", sa.String, nullable=False),
        sa.Column(
            "profile",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("profile_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("clerk_user_id", name="users_clerk_user_id_key"),
        sa.UniqueConstraint("email", name="users_email_key"),
    )
    op.create_index("ix_users_clerk", "users", ["clerk_user_id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.execute(
        "create trigger users_set_updated_at before update on users "
        "for each row execute function set_updated_at()"
    )

    # articles
    op.create_table(
        "articles",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_type", sa.String, nullable=False),
        sa.Column("source_name", sa.String, nullable=False),
        sa.Column("external_id", sa.String, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("author", sa.Text, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_text", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "raw",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_type in ('rss','youtube','web_search')",
            name="articles_source_type_check",
        ),
        sa.UniqueConstraint("source_type", "external_id", name="articles_source_external_uk"),
    )
    op.create_index("ix_articles_source_pub", "articles", ["source_type", "published_at"])
    op.create_index("ix_articles_pub", "articles", ["published_at"])
    op.execute(
        "create trigger articles_set_updated_at before update on articles "
        "for each row execute function set_updated_at()"
    )

    # digests
    op.create_table(
        "digests",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("intro", sa.Text, nullable=True),
        sa.Column(
            "ranked_articles",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "top_themes",
            postgresql.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("article_count", sa.Integer, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('pending','generated','emailed','failed')",
            name="digests_status_check",
        ),
    )
    op.create_index("ix_digests_user_gen", "digests", ["user_id", "generated_at"])
    op.create_index("ix_digests_status", "digests", ["status"])

    # email_sends
    op.create_table(
        "email_sends",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "digest_id",
            sa.BigInteger,
            sa.ForeignKey("digests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String, nullable=False, server_default="resend"),
        sa.Column("to_address", sa.String, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("provider_message_id", sa.String, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.CheckConstraint(
            "status in ('pending','sent','failed','bounced')",
            name="email_sends_status_check",
        ),
    )
    op.create_index("ix_email_sends_user_sent", "email_sends", ["user_id", "sent_at"])
    op.create_index("ix_email_sends_digest", "email_sends", ["digest_id"])

    # audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("agent_name", sa.String, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decision_type", sa.String, nullable=False),
        sa.Column("input_summary", sa.Text, nullable=True),
        sa.Column("output_summary", sa.Text, nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("ix_audit_agent_ts", "audit_logs", ["agent_name", "timestamp"])
    op.create_index(
        "ix_audit_user_ts_partial",
        "audit_logs",
        ["user_id", "timestamp"],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_audit_user_ts_partial", table_name="audit_logs")
    op.drop_index("ix_audit_agent_ts", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_email_sends_digest", table_name="email_sends")
    op.drop_index("ix_email_sends_user_sent", table_name="email_sends")
    op.drop_table("email_sends")

    op.drop_index("ix_digests_status", table_name="digests")
    op.drop_index("ix_digests_user_gen", table_name="digests")
    op.drop_table("digests")

    op.execute("drop trigger if exists articles_set_updated_at on articles")
    op.drop_index("ix_articles_pub", table_name="articles")
    op.drop_index("ix_articles_source_pub", table_name="articles")
    op.drop_table("articles")

    op.execute("drop trigger if exists users_set_updated_at on users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_clerk", table_name="users")
    op.drop_table("users")

    op.execute("drop function if exists set_updated_at()")
