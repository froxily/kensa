"""Baseline: pgvector extension and the workspaces table (with the default workspace).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-29
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_WORKSPACE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    workspaces = op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
        sa.UniqueConstraint("name", name=op.f("uq_workspaces_name")),
    )
    op.bulk_insert(workspaces, [{"id": DEFAULT_WORKSPACE_ID, "name": "default"}])


def downgrade() -> None:
    op.drop_table("workspaces")
    op.execute("DROP EXTENSION IF EXISTS vector")
