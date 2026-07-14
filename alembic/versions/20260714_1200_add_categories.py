"""add categories

Revision ID: 20260714_1200
Revises: 20260713_0946
Create Date: 2026-07-14 12:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260714_1200"
down_revision: str | None = "20260713_0946"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
            name=op.f("fk_categories_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint(
            "organization_id",
            "normalized_name",
            name="uq_categories_organization_id_normalized_name",
        ),
    )
    op.create_index("ix_categories_is_active", "categories", ["is_active"], unique=False)
    op.create_index(
        "ix_categories_organization_id",
        "categories",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_categories_organization_id", table_name="categories")
    op.drop_index("ix_categories_is_active", table_name="categories")
    op.drop_table("categories")
