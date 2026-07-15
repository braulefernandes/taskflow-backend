"""add ticket comments and history

Revision ID: 20260715_1500
Revises: 20260714_1600
Create Date: 2026-07-15 15:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260715_1500"
down_revision: str | None = "20260714_1600"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ticket_history_action_enum = postgresql.ENUM(
    "CREATED",
    "TITLE_CHANGED",
    "DESCRIPTION_CHANGED",
    "CATEGORY_CHANGED",
    "PRIORITY_CHANGED",
    "DUE_DATE_CHANGED",
    "ASSIGNED",
    "ASSIGNEE_CHANGED",
    "ASSIGNEE_REMOVED",
    "STATUS_CHANGED",
    "COMPLETED",
    "REOPENED",
    "CANCELLED",
    name="ticket_history_action",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    ticket_history_action_enum.create(bind, checkfirst=True)

    op.create_table(
        "ticket_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
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
            "length(trim(content)) >= 1 AND length(content) <= 5000",
            name=op.f("ck_ticket_comments_content_length"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_ticket_comments_ticket_id_tickets"),
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_ticket_comments_author_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_comments")),
    )
    op.create_index(
        "ix_ticket_comments_ticket_id_created_at",
        "ticket_comments",
        ["ticket_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "ticket_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", ticket_history_action_enum, nullable=False),
        sa.Column("field_name", sa.String(length=100), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "old_value IS NULL OR length(old_value) <= 2000",
            name=op.f("ck_ticket_history_old_value_length"),
        ),
        sa.CheckConstraint(
            "new_value IS NULL OR length(new_value) <= 2000",
            name=op.f("ck_ticket_history_new_value_length"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_ticket_history_ticket_id_tickets"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_ticket_history_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_history")),
    )
    op.create_index(
        "ix_ticket_history_ticket_id_created_at",
        "ticket_history",
        ["ticket_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ticket_history_ticket_id_created_at", table_name="ticket_history")
    op.drop_table("ticket_history")
    op.drop_index(
        "ix_ticket_comments_ticket_id_created_at", table_name="ticket_comments"
    )
    op.drop_table("ticket_comments")
    bind = op.get_bind()
    ticket_history_action_enum.drop(bind, checkfirst=True)
