"""root-cause statuses separate from evidence validity (M5.1, D-040)

* ``diagnoses.verification_status`` moves from verified / supported / contradicted / unknown to
  corroborated / plausible / conflicting / not_established. Only a cause stated in the log, cited,
  and uncontested is corroborated; genuine citations alone no longer earn the strongest status.
* Existing rows are relabelled conservatively, because no cause check ever ran on them:
  verified and supported become plausible, contradicted becomes conflicting, unknown becomes
  not_established. Each relabelled row gets a note saying so; nothing else changes.

Revision ID: 0007_cause_status
Revises: 0006_withdrawn
Create Date: 2026-10-30 22:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_cause_status"
down_revision: str | Sequence[str] | None = "0006_withdrawn"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW = "verification_status IN ('corroborated', 'plausible', 'conflicting', 'not_established')"
OLD = "verification_status IN ('verified', 'supported', 'contradicted', 'unknown')"
UPGRADE = {
    "verified": "plausible",
    "supported": "plausible",
    "contradicted": "conflicting",
    "unknown": "not_established",
}
DOWNGRADE = {"corroborated": "verified", "plausible": "supported", "conflicting": "contradicted"}


RELABEL = sa.text(
    "UPDATE diagnoses SET verification_status = :new, "
    "verification_notes = array_append(verification_notes, :note) "
    "WHERE verification_status = :old"
)
RESTORE = sa.text(
    "UPDATE diagnoses SET verification_status = :old WHERE verification_status = :new"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_diagnoses_verification"), "diagnoses", type_="check")
    for old, new in UPGRADE.items():
        note = (
            f"Status relabelled from '{old}' to '{new}' by migration 0007 (M5.1): this report "
            "predates the cause check, so its citations were checked but its cause was not."
        )
        op.get_bind().execute(RELABEL, {"old": old, "new": new, "note": note})
    op.create_check_constraint(op.f("ck_diagnoses_verification"), "diagnoses", NEW)


def downgrade() -> None:
    op.drop_constraint(op.f("ck_diagnoses_verification"), "diagnoses", type_="check")
    for new, old in {**DOWNGRADE, "not_established": "unknown"}.items():
        op.get_bind().execute(RESTORE, {"old": old, "new": new})
    op.create_check_constraint(op.f("ck_diagnoses_verification"), "diagnoses", OLD)
