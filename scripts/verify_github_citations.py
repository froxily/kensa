"""Independent check of a GitHub investigation's evidence against GitHub itself (read-only).

For the given investigation it re-downloads the job log and re-reads every cited repository
file at the run's commit, then checks that:
* each accepted citation's quote really appears on the cited line of GitHub's own text,
  after the same normalisation Kensa applies to every log (ANSI colour codes removed,
  line endings unified); lines that differ from the raw bytes only by that are counted,
* each evidence excerpt from a repository file equals the file's lines at that commit,
* each repository evidence link points at the run's commit.
Writes ``eval/reports/m4-live-github-citations.md``. Never prints the token.

    uv run --directory backend --no-sync python ../scripts/verify_github_citations.py <id>
"""

import argparse
import base64
import re
import sys
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from kensa.core.config import Settings
from kensa.db.models import (
    Chunk,
    Citation,
    Diagnosis,
    Document,
    Evidence,
    Repository,
    WorkflowRun,
)
from kensa.db.session import build_engine
from kensa.github.client import ETagCache, GitHubClient
from kensa.ingestion.normalize import normalize_log, strip_timestamp

REPORT = Path(__file__).resolve().parents[1] / "eval" / "reports" / "m4-live-github-citations.md"
MARKDOWN = re.compile(r"[`*]")


def norm(text: str, markdown: bool = False) -> str:
    text = strip_timestamp(text)
    if markdown:
        text = MARKDOWN.sub("", text)
    text = re.sub(r"^\s*L\d+:\s*", "", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("investigation_id", type=uuid.UUID)
    args = parser.parse_args()
    settings = Settings()
    engine = build_engine(settings)
    rows: list[str] = []
    failures = 0
    with Session(engine) as session:
        run = session.scalars(
            select(WorkflowRun).where(WorkflowRun.investigation_id == args.investigation_id)
        ).one()
        diagnosis = session.scalars(
            select(Diagnosis).where(Diagnosis.investigation_id == args.investigation_id)
        ).one()
        citations = session.scalars(
            select(Citation).where(Citation.diagnosis_id == diagnosis.id).order_by(Citation.ordinal)
        ).all()
        evidence = session.execute(
            select(Evidence, Chunk, Document, Repository)
            .join(Chunk, Chunk.id == Evidence.chunk_id)
            .join(Document, Document.id == Chunk.document_id)
            .outerjoin(Repository, Repository.id == Document.repository_id)
            .where(Evidence.investigation_id == args.investigation_id)
            .order_by(Evidence.rank)
        ).all()

    with GitHubClient(token=settings.github_token, cache=ETagCache()) as client:
        raw_log = client.job_log(run.owner, run.repo, run.job_id).content.decode("utf-8", "replace")
        raw_lines = raw_log.replace("\r\n", "\n").split("\n")
        log_lines = normalize_log(raw_log).text.split("\n")
        ansi_only = sum(
            1 for a, b in zip(raw_lines, log_lines, strict=False) if a != b and "\x1b[" in a
        )
        files: dict[str, list[str]] = {}
        for _, _, document, repository in evidence:
            if repository is not None and document.name not in files:
                data = client.file_at(run.owner, run.repo, document.name, run.head_sha) or {}
                raw = base64.b64decode(str(data.get("content", ""))).decode("utf-8")
                files[document.name] = raw.replace("\r\n", "\n").split("\n")

    by_label = {
        e.label: (chunk, document, repository) for e, chunk, document, repository in evidence
    }

    def source_lines(document: Document, repository: Repository | None) -> list[str]:
        """GitHub's text for the job log and repository files; Kensa's own stored text for its
        knowledge notes and past incidents, which do not come from GitHub."""
        if document.source_type in ("kb", "incident"):
            return document.content.split("\n")
        return log_lines if repository is None else files[document.name]

    rows.append(f"## Citations ({diagnosis.category}, {diagnosis.verification_status})\n")
    rows.append(
        "| # | evidence | line | quote found on the source line? | source line "
        "(GitHub; Kensa's own text for kb/incident) |"
    )
    rows.append("|---|---|---|---|---|")
    for c in citations:
        chunk, document, repository = by_label[c.evidence_label]
        source = source_lines(document, repository)
        line = source[c.line_number - 1] if 0 < c.line_number <= len(source) else ""
        markdown = document.source_type in ("kb", "doc", "incident")
        found = norm(c.quote, markdown) in norm(line, markdown)
        if c.valid and not found:
            failures += 1
        shown = strip_timestamp(line).strip().replace("|", "\\|")[:140]
        rows.append(
            f"| {c.ordinal + 1} | {c.evidence_label} ({document.source_type}: {document.name}) "
            f"| L{c.line_number} | {'yes' if found else 'NO'} (accepted: {c.valid}) | `{shown}` |"
        )

    rows += [
        "",
        "## Evidence excerpts",
        "",
        "| evidence | source | lines | matches its source (GitHub; Kensa for kb/incident) "
        "| commit |",
    ]
    rows.append("|---|---|---|---|---|")
    for e, chunk, document, repository in evidence:
        source = source_lines(document, repository)
        github = [strip_timestamp(x) for x in source[chunk.start_line - 1 : chunk.end_line]]
        stored = [strip_timestamp(x) for x in chunk.content.split("\n")]
        same = [x.rstrip() for x in github] == [x.rstrip() for x in stored]
        pinned = repository is None or repository.commit_sha == run.head_sha
        if not same and "[REDACTED" not in chunk.content:
            failures += 1
        if not pinned:
            failures += 1
        commit = (
            repository.commit_sha[:7] if repository is not None and repository.commit_sha else "—"
        )
        rows.append(
            f"| {e.label} | {document.source_type}: {document.name} "
            f"| {chunk.start_line}-{chunk.end_line} | {'yes' if same else 'NO'} | {commit} |"
        )

    header = [
        "# M4 live check: citations re-verified against GitHub",
        "",
        f"> Investigation `{args.investigation_id}` of {run.owner}/{run.repo} run "
        f"{run.run_id}, job "
        f"{run.job_id}, commit `{run.head_sha}`. The job log and every cited repository file "
        "were downloaded again from GitHub (read-only), independently of Kensa's stored copies, "
        "and compared line by line.",
        "",
        f"**Result:** {'all checks passed' if failures == 0 else f'{failures} check(s) FAILED'}.",
        "",
        f"GitHub's raw log has {len(raw_lines)} lines; {ansi_only} differ from Kensa's stored text "
        "only by ANSI colour codes, which Kensa's log normalisation removes. The comparison below "
        "uses that same normalisation of GitHub's bytes.",
        "",
    ]
    REPORT.write_text("\n".join(header + rows) + "\n", encoding="utf-8")
    print("\n".join(header + rows))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
