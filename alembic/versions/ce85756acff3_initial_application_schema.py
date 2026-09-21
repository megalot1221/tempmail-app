"""initial application schema

Revision ID: ce85756acff3
Revises:
Create Date: 2026-09-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ce85756acff3"
down_revision: Union[str, Sequence[str], None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_users_username",
        "users",
        ["username"],
        unique=True,
    )
    op.create_index(
        "ix_users_email",
        "users",
        ["email"],
        unique=True,
    )
    op.create_index(
        "ix_users_role",
        "users",
        ["role"],
        unique=False,
    )

    op.create_table(
        "guest_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_token", sa.String(length=128), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_guest_sessions_session_token",
        "guest_sessions",
        ["session_token"],
        unique=True,
    )

    op.create_table(
        "domains",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("verification_token", sa.String(length=255), nullable=True),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_domains_domain",
        "domains",
        ["domain"],
        unique=True,
    )
    op.create_index(
        "ix_domains_status",
        "domains",
        ["status"],
        unique=False,
    )

    op.create_table(
        "analytics_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("registered_users", sa.Integer(), nullable=False),
        sa.Column("emails_generated", sa.Integer(), nullable=False),
        sa.Column("emails_received", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_analytics_daily_date",
        "analytics_daily",
        ["date"],
        unique=True,
    )

    op.create_table(
        "activity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("guest_session_id", sa.Integer(), nullable=True),
        sa.Column("event", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["guest_session_id"],
            ["guest_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_activity_event",
        "activity",
        ["event"],
        unique=False,
    )
    op.create_index(
        "ix_activity_user_id",
        "activity",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_activity_guest_session_id",
        "activity",
        ["guest_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_activity_created_at",
        "activity",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "mailboxes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("tempmail_token", sa.String(length=255), nullable=False),
        sa.Column("mailbox_type", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("guest_session_id", sa.Integer(), nullable=True),
        sa.Column("domain_id", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["domain_id"],
            ["domains.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["guest_session_id"],
            ["guest_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "email",
            name="uq_user_mailbox",
        ),
    )

    op.create_index(
        "ix_mailboxes_email",
        "mailboxes",
        ["email"],
        unique=True,
    )
    op.create_index(
        "ix_mailboxes_tempmail_token",
        "mailboxes",
        ["tempmail_token"],
        unique=True,
    )
    op.create_index(
        "ix_mailboxes_mailbox_type",
        "mailboxes",
        ["mailbox_type"],
        unique=False,
    )
    op.create_index(
        "ix_mailboxes_user_id",
        "mailboxes",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_mailboxes_guest_session_id",
        "mailboxes",
        ["guest_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_mailboxes_domain_id",
        "mailboxes",
        ["domain_id"],
        unique=False,
    )
    op.create_index(
        "ix_mailboxes_is_active",
        "mailboxes",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("mailboxes")
    op.drop_table("activity")
    op.drop_table("analytics_daily")
    op.drop_table("domains")
    op.drop_table("guest_sessions")
    op.drop_table("users")
