"""M2: incremental indexing, hybrid retrieval scope and channels, degradation, incidents."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from kensa.agents.pipeline import run_investigation
from kensa.analysis.signatures import extract_signatures
from kensa.db.models import DEFAULT_WORKSPACE_ID, AgentEvent, Chunk, Document
from kensa.indexing.service import (
    embed_pending,
    ensure_repository,
    index_directory,
    index_knowledge,
)
from kensa.inference.base import ModelUnavailableError
from kensa.inference.embeddings import HashingEmbedder
from kensa.inference.mock import MockProvider
from kensa.investigations.service import NewInvestigation, create_investigation
from kensa.jobs import queue
from kensa.retrieval.search import retrieve

pytestmark = pytest.mark.db
EMBEDDER = HashingEmbedder(1024)
LOG = (
    "##[group]Run npm run build\n"
    "> next build\n"
    "Error: Missing required environment variable: NEXT_PUBLIC_API_ORIGIN\n"
    "##[error]Process completed with exit code 1.\n"
)
WORKFLOW = (
    "name: ci\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    env:\n"
    "      NODE_ENV: production\n    steps:\n      - run: npm ci\n      - run: npm run build\n"
)


def _write_repo(root: Path, workflow: str = WORKFLOW) -> None:
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(workflow, encoding="utf-8")
    (root / ".env.example").write_text("NEXT_PUBLIC_API_ORIGIN=https://api.example.test\n")
    (root / "README.md").write_text("# Web\n\n## Configuration\nSet NEXT_PUBLIC_API_ORIGIN.\n")
    (root / "node_modules").mkdir(exist_ok=True)
    (root / "node_modules" / "ignored.js").write_text("ignored")


def _index(engine: Engine, root: Path, name: str = "acme/web") -> tuple[uuid.UUID, dict[str, int]]:
    with Session(engine) as session, session.begin():
        repo = ensure_repository(session, DEFAULT_WORKSPACE_ID, name)
        result = index_directory(session, DEFAULT_WORKSPACE_ID, repo.id, root)
        embed_pending(session, EMBEDDER, DEFAULT_WORKSPACE_ID)
        return repo.id, result.counts


def _investigate(engine: Engine, repository_id: uuid.UUID | None, log: str = LOG) -> uuid.UUID:
    with Session(engine) as session, session.begin():
        new = NewInvestigation(None, "paste", "mock", "build.log", log, repository_id)
        return create_investigation(session, DEFAULT_WORKSPACE_ID, new, None).id


def test_repository_indexing_is_incremental(db_engine: Engine, tmp_path: Path) -> None:
    _write_repo(tmp_path)
    repo_id, first = _index(db_engine, tmp_path)
    assert first == {"created": 3}  # node_modules skipped
    _, second = _index(db_engine, tmp_path)
    assert second == {"unchanged": 3}

    (tmp_path / "README.md").write_text("# Web\nchanged\n")
    (tmp_path / ".env.example").unlink()
    _, third = _index(db_engine, tmp_path)
    assert third["updated"] == 1
    assert third["unchanged"] == 1
    assert third["removed"] == 1
    with Session(db_engine) as session:
        names = session.scalars(
            select(Document.name).where(Document.repository_id == repo_id)
        ).all()
        assert sorted(names) == [".github/workflows/ci.yml", "README.md"]
        # The re-chunked README was embedded again by the helper: nothing is left unembedded.
        assert (
            session.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.embedding_model.is_(None))
            )
            == 0
        )


def test_repository_files_are_redacted(db_engine: Engine, tmp_path: Path) -> None:
    secret = "ghp_" + "Rr1Tt2Yy3Uu4Ii5Oo6Pp7Aa8Ss9Dd0Ff1Gg2Hh3"
    _write_repo(tmp_path, WORKFLOW + f"      - run: echo token={secret}\n")
    _index(db_engine, tmp_path)
    with Session(db_engine) as session:
        assert all(secret not in c for c in session.scalars(select(Chunk.content)))


def test_hybrid_retrieval_reaches_repository_and_knowledge(
    db_engine: Engine, tmp_path: Path
) -> None:
    _write_repo(tmp_path)
    repo_id, _ = _index(db_engine, tmp_path)
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "env.md").write_text("# Missing environment variables\nCheck the workflow env block.\n")
    with Session(db_engine) as session, session.begin():
        index_knowledge(session, DEFAULT_WORKSPACE_ID, kb)
        embed_pending(session, EMBEDDER, DEFAULT_WORKSPACE_ID)
    investigation_id = _investigate(db_engine, repo_id)

    sigs = extract_signatures(LOG.splitlines())
    with Session(db_engine) as session, session.begin():
        embed_pending(session, EMBEDDER, DEFAULT_WORKSPACE_ID)
        query = EMBEDDER.embed_query("Missing required environment variable NEXT_PUBLIC_API_ORIGIN")
        hybrid = retrieve(
            session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            investigation_id=investigation_id,
            signatures=sigs,
            repository_id=repo_id,
            query_vector=query,
        )
        sources = {c.source_type for c in hybrid}
        assert {"log", "code"} <= sources
        assert any("vector" in c.channels for c in hybrid)

        m1_style = retrieve(
            session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            investigation_id=investigation_id,
            signatures=sigs,
            repository_id=repo_id,
            channels=frozenset({"signature", "fts"}),
        )
        assert all("vector" not in c.channels for c in m1_style)


def test_scope_excludes_other_repositories(db_engine: Engine, tmp_path: Path) -> None:
    mine, other = tmp_path / "mine", tmp_path / "other"
    _write_repo(mine)
    _write_repo(other)
    my_repo, _ = _index(db_engine, mine, "acme/mine")
    other_repo, _ = _index(db_engine, other, "acme/other")
    investigation_id = _investigate(db_engine, my_repo)
    with Session(db_engine) as session, session.begin():
        embed_pending(session, EMBEDDER, DEFAULT_WORKSPACE_ID)
        found = retrieve(
            session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            investigation_id=investigation_id,
            signatures=extract_signatures(LOG.splitlines()),
            repository_id=my_repo,
            query_vector=EMBEDDER.embed_query("NEXT_PUBLIC_API_ORIGIN"),
        )
        other_docs = set(
            session.scalars(select(Document.id).where(Document.repository_id == other_repo))
        )
    assert found
    assert not {c.document_id for c in found} & other_docs


class FailingEmbedder(HashingEmbedder):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise ModelUnavailableError("embedding model down")


def _run(engine: Engine, investigation_id: uuid.UUID, embedder: HashingEmbedder) -> None:
    with Session(engine) as session, session.begin():
        lease = queue.claim(session, "test", 30)
    assert lease is not None
    assert lease.investigation_id == investigation_id
    run_investigation(
        lease, engine, MockProvider(), num_ctx=8192, embedder=embedder, index_incidents=True
    )
    with Session(engine) as session, session.begin():
        queue.complete(session, lease)


def test_embedding_failure_degrades_to_keyword_search(db_engine: Engine) -> None:
    investigation_id = _investigate(db_engine, None)
    _run(db_engine, investigation_id, FailingEmbedder(1024))
    with Session(db_engine) as session:
        events = session.scalars(
            select(AgentEvent)
            .where(AgentEvent.investigation_id == investigation_id)
            .order_by(AgentEvent.seq)
        ).all()
    index = [e for e in events if e.node == "index"]
    assert index[0].event_type == "failed"
    assert "full-text" in index[0].summary
    assert events[-1].node in {"report", "index"}
    assert any(e.node == "report" and e.event_type == "completed" for e in events)


def test_verified_investigations_become_incidents_but_never_their_own_evidence(
    db_engine: Engine,
) -> None:
    first = _investigate(db_engine, None)
    _run(db_engine, first, EMBEDDER)
    with Session(db_engine) as session:
        incident = session.scalars(select(Document).where(Document.source_type == "incident")).one()
        assert incident.name == f"incident/{first}"
        assert "NEXT_PUBLIC_API_ORIGIN" in incident.content or "environment" in incident.content
    second = _investigate(db_engine, None, LOG.replace("exit code 1", "exit code 1 (rerun)"))
    sigs = extract_signatures(LOG.splitlines())
    with Session(db_engine) as session, session.begin():
        embed_pending(session, EMBEDDER, DEFAULT_WORKSPACE_ID)
        query = EMBEDDER.embed_query("Missing required environment variable")
        for target, should_see in ((second, True), (first, False)):
            found = retrieve(
                session,
                workspace_id=DEFAULT_WORKSPACE_ID,
                investigation_id=target,
                signatures=sigs,
                query_vector=query,
            )
            assert any(c.source_type == "incident" for c in found) is should_see


def test_a_reinvestigation_of_the_same_log_never_sees_its_earlier_incident(
    db_engine: Engine,
) -> None:
    # Found in the M4 live check: investigating the same failed job twice made the first
    # report's own conclusion evidence for the second (self-confirmation).
    first = _investigate(db_engine, None)
    _run(db_engine, first, EMBEDDER)
    again = _investigate(db_engine, None)  # the identical log
    sigs = extract_signatures(LOG.splitlines())
    with Session(db_engine) as session, session.begin():
        embed_pending(session, EMBEDDER, DEFAULT_WORKSPACE_ID)
        query = EMBEDDER.embed_query("Missing required environment variable")
        found = retrieve(
            session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            investigation_id=again,
            signatures=sigs,
            query_vector=query,
        )
    assert found
    assert not any(c.source_type == "incident" for c in found)
