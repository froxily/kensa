"""Re-check stored remediation diffs with today's edit checks; withdraw named investigations'
proposals as unsafe or non-actionable (M5). Nothing is deleted: proposals, diffs and history
stay, with the reason, the time and a timeline entry recorded.

    # report only
    uv run --directory backend --no-sync python ../scripts/withdraw_unsafe_proposals.py
    # withdraw the proposals of the named investigations
    uv run --directory backend --no-sync python ../scripts/withdraw_unsafe_proposals.py \\
        --apply <investigation-id> [<investigation-id> ...]
"""

import argparse
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from kensa.agents.remediation import recheck_proposal
from kensa.core.config import Settings
from kensa.db.models import DEFAULT_WORKSPACE_ID, Document, RemediationProposal
from kensa.db.session import build_engine
from kensa.investigations.service import withdraw_proposals

UNSAFE = (
    "unsafe under the edit checks added after the M4 live runs ({reason}); kept for the audit "
    "trail, never actionable"
)
NON_ACTIONABLE = (
    "non-actionable: produced in the same run as an unsafe edit, before the M4 edit-safety "
    "fixes, from a root cause that is probably incomplete; kept for the audit trail"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", nargs="*", type=uuid.UUID, default=[])
    args = parser.parse_args()
    engine = build_engine(Settings())
    verdicts: dict[uuid.UUID, dict[int, str | None]] = {}
    with Session(engine) as session:
        rows = session.execute(
            select(RemediationProposal, Document.name, Document.content)
            .join(Document, Document.id == RemediationProposal.target_document_id)
            .where(RemediationProposal.diff.is_not(None))
            .order_by(RemediationProposal.created_at)
        ).all()
        for proposal, path, original in rows:
            verdict = recheck_proposal(path, original, proposal.diff or "")
            verdicts.setdefault(proposal.investigation_id, {})[proposal.ordinal] = verdict
            print(
                f"{proposal.investigation_id} proposal {proposal.ordinal} ({proposal.status}) "
                f"{path}: {verdict or 'passes the current checks'}"
            )
    for investigation_id in args.apply:
        with Session(engine) as session, session.begin():
            proposals = session.scalars(
                select(RemediationProposal).where(
                    RemediationProposal.investigation_id == investigation_id
                )
            ).all()
            unsafe = verdicts.get(investigation_id, {})
            reasons = {
                p.ordinal: UNSAFE.format(reason=unsafe[p.ordinal])
                if unsafe.get(p.ordinal)
                else NON_ACTIONABLE
                for p in proposals
            }
            result = withdraw_proposals(session, DEFAULT_WORKSPACE_ID, investigation_id, reasons)
        if result is None:
            print(f"{investigation_id}: not found")
            return 1
        print(
            f"{investigation_id}: withdrew {result.withdrawn}, left as decided {result.skipped}, "
            f"investigation closed: {result.closed}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
