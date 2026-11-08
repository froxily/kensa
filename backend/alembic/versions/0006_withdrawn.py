"""withdrawn proposals

* ``remediation_proposals.status`` gains ``withdrawn``: a proposal marked unsafe or
  non-actionable after the fact. It is never deleted; its diff and text stay for the audit
  trail, with ``withdrawn_reason`` and ``withdrawn_at`` (a CHECK ties the reason to the status).

Revision ID: 0006_withdrawn
Revises: 0005_github
Create Date: 2026-10-30 19:29:37.108233
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_withdrawn"
down_revision: str | Sequence[str] | None = "0005_github"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_M6 = "status IN ('proposed', 'approved', 'rejected', 'withdrawn')"
STATUS_M5 = "status IN ('proposed', 'approved', 'rejected')"
REASON = "(status = 'withdrawn') = (withdrawn_reason IS NOT NULL)"


def upgrade() -> None:
    op.add_column("remediation_proposals", sa.Column("withdrawn_reason", sa.Text(), nullable=True))
    op.add_column(
        "remediation_proposals",
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint(
        op.f("ck_remediation_proposals_status"), "remediation_proposals", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_remediation_proposals_status"), "remediation_proposals", STATUS_M6
    )
    op.create_check_constraint(
        op.f("ck_remediation_proposals_withdrawn_reason"), "remediation_proposals", REASON
    )


def downgrade() -> None:
    # Withdrawn proposals cannot exist before M5; they fall back to rejected.
    op.execute("UPDATE remediation_proposals SET status = 'rejected' WHERE status = 'withdrawn'")
    op.drop_constraint(
        op.f("ck_remediation_proposals_withdrawn_reason"), "remediation_proposals", type_="check"
    )
    op.drop_constraint(
        op.f("ck_remediation_proposals_status"), "remediation_proposals", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_remediation_proposals_status"), "remediation_proposals", STATUS_M5
    )
    op.drop_column("remediation_proposals", "withdrawn_at")
    op.drop_column("remediation_proposals", "withdrawn_reason")
