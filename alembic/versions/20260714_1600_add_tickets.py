"""add tickets

Revision ID: 20260714_1600
Revises: 20260714_1200
Create Date: 2026-07-14 16:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260714_1600"
down_revision: str | None = "20260714_1200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ticket_status_enum = postgresql.ENUM(
    "PENDING",
    "IN_PROGRESS",
    "WAITING",
    "COMPLETED",
    "CANCELLED",
    name="ticket_status",
    create_type=False,
)
ticket_priority_enum = postgresql.ENUM(
    "LOW",
    "MEDIUM",
    "HIGH",
    "URGENT",
    name="ticket_priority",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    ticket_status_enum.create(bind, checkfirst=True)
    ticket_priority_enum.create(bind, checkfirst=True)
    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status", ticket_status_enum, server_default="PENDING", nullable=False
        ),
        sa.Column(
            "priority", ticket_priority_enum, server_default="MEDIUM", nullable=False
        ),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name=op.f("fk_tickets_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            ondelete="RESTRICT",
            name=op.f("fk_tickets_category_id_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_tickets_requester_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_tickets_assignee_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
    )
    for column in (
        "organization_id",
        "status",
        "priority",
        "category_id",
        "assignee_id",
        "due_date",
        "created_at",
    ):
        op.create_index(f"ix_tickets_{column}", "tickets", [column], unique=False)


def downgrade() -> None:
    for column in reversed(
        (
            "organization_id",
            "status",
            "priority",
            "category_id",
            "assignee_id",
            "due_date",
            "created_at",
        )
    ):
        op.drop_index(f"ix_tickets_{column}", table_name="tickets")
    op.drop_table("tickets")
    bind = op.get_bind()
    ticket_priority_enum.drop(bind, checkfirst=True)
    ticket_status_enum.drop(bind, checkfirst=True)
