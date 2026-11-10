"""Fingerprint investigations created before v1.1 (D-053). Idempotent; run it any time.

    uv run --directory backend --no-sync python ../scripts/backfill_fingerprints.py

Recomputes fingerprints from each stored (redacted) log exactly as Kensa does at creation:
rule-derived signatures and stated causes only, never model output. Nothing else changes.
"""

from sqlalchemy.orm import Session

from kensa.core.config import get_settings
from kensa.db.models import DEFAULT_WORKSPACE_ID
from kensa.db.session import build_engine
from kensa.history.fingerprints import backfill


def main() -> None:
    engine = build_engine(get_settings())
    total, after = 0, None
    while True:
        with Session(engine) as session, session.begin():
            done = backfill(session, DEFAULT_WORKSPACE_ID, limit=200, after=after)
        if not done:
            break
        total += len(done)
        after = done[-1]
    print(f"Checked {total} investigation(s) without fingerprints.")


if __name__ == "__main__":
    main()
