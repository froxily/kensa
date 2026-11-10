"""fingerprint kind: exact fingerprints claim a recurrence, approximate ones never do (v1.1.0)

* ``failure_fingerprints.kind``: ``exact`` (identified by a subject the log names, or a line
  with a distinctive identifier) or ``approximate`` (only used to find similar failures).
  Existing rows are older fingerprint versions, which matching ignores (D-057).

Revision ID: 0012_fingerprint_kind
Revises: 0011_analytics
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_fingerprint_kind"
down_revision: str | Sequence[str] | None = "0011_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "failure_fingerprints",
        sa.Column("kind", sa.String(length=16), server_default="exact", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_failure_fingerprints_kind"),
        "failure_fingerprints",
        "kind IN ('exact', 'approximate')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_failure_fingerprints_kind"), "failure_fingerprints", type_="check")
    op.drop_column("failure_fingerprints", "kind")
