"""Indexing of repository files, knowledge notes and past incidents (M2).

Documents are identified per scope (D-022): a repository file by its path, a workspace note or
incident by its name. Re-indexing is incremental: an unchanged content hash is skipped, a changed
file is re-chunked in place, and files that disappeared from a repository are removed.
Embedding is a separate pass (``embed_pending``) so it never overlaps with LLM inference.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from kensa.db.models import Chunk, Document, ErrorSignature, Repository
from kensa.inference.embeddings import Embedder
from kensa.ingestion.files import chunk_file, source_type_for
from kensa.ingestion.normalize import LogRejectedError, normalize_log, strip_timestamp
from kensa.ingestion.redaction import redact

MAX_FILE_BYTES = 200_000
MAX_FILES = 500
SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "target",
    "__pycache__",
    ".next",
    ".mypy_cache",
    ".pytest_cache",
    "vendor",
}
TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".cs",
    ".rb",
    ".php",
    ".yml",
    ".yaml",
    ".toml",
    ".json",
    ".ini",
    ".cfg",
    ".conf",
    ".xml",
    ".gradle",
    ".properties",
    ".md",
    ".markdown",
    ".rst",
    ".txt",
    ".sh",
    ".ps1",
    ".sql",
    ".env",
    ".example",
    ".lock",
    ".mod",
    ".sum",
    ".csproj",
    ".sln",
}
TEXT_NAMES = {"Dockerfile", "Makefile", "Procfile", ".dockerignore", ".gitignore", ".env.example"}

Outcome = Literal["created", "updated", "unchanged", "skipped"]


@dataclass
class IndexResult:
    counts: dict[str, int] = field(default_factory=dict)
    document_ids: list[uuid.UUID] = field(default_factory=list)

    def add(self, outcome: Outcome, document_id: uuid.UUID | None) -> None:
        self.counts[outcome] = self.counts.get(outcome, 0) + 1
        if document_id is not None and outcome in ("created", "updated"):
            self.document_ids.append(document_id)


def ensure_repository(
    session: Session,
    workspace_id: uuid.UUID,
    name: str,
    provider: str = "local",
    commit_sha: str | None = None,
) -> Repository:
    """A local repository by name, or a GitHub repository snapshot by name and commit."""
    commit_filter = (
        Repository.commit_sha.is_(None)
        if commit_sha is None
        else Repository.commit_sha == commit_sha
    )
    repository = session.scalars(
        select(Repository).where(
            Repository.workspace_id == workspace_id,
            Repository.provider == provider,
            Repository.name == name,
            commit_filter,
        )
    ).one_or_none()
    if repository is None:
        repository = Repository(
            workspace_id=workspace_id, provider=provider, name=name[:200], commit_sha=commit_sha
        )
        session.add(repository)
        session.flush()
    return repository


def upsert_document(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    repository_id: uuid.UUID | None,
    source_type: str,
    name: str,
    content: str,
) -> tuple[Outcome, uuid.UUID | None]:
    """Redact, chunk and store one file. Returns what happened and the document id."""
    try:
        normalized = normalize_log(content)
    except LogRejectedError:
        return "skipped", None
    redacted = redact(normalized.text)
    lines = redacted.text.split("\n")
    content_hash = hashlib.sha256(redacted.text.encode("utf-8")).hexdigest()

    query = select(Document).where(
        Document.workspace_id == workspace_id,
        Document.investigation_id.is_(None),
        Document.name == name,
    )
    if repository_id is None:
        query = query.where(Document.repository_id.is_(None), Document.source_type == source_type)
    else:
        query = query.where(Document.repository_id == repository_id)
    document = session.scalars(query).one_or_none()
    if document is not None and document.content_hash == content_hash:
        return "unchanged", document.id

    outcome: Outcome = "updated" if document is not None else "created"
    if document is None:
        document = Document(workspace_id=workspace_id, repository_id=repository_id, name=name)
        session.add(document)
    else:
        session.execute(delete(ErrorSignature).where(ErrorSignature.document_id == document.id))
        session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    document.source_type = source_type
    document.content = redacted.text
    document.content_hash = content_hash
    document.byte_size = len(redacted.text.encode("utf-8"))
    document.line_count = len(lines)
    document.redaction_count = redacted.total
    session.flush()
    session.add_all(
        Chunk(
            workspace_id=workspace_id,
            document_id=document.id,
            ordinal=d.ordinal,
            kind=d.kind,
            step_name=d.step_name,
            start_line=d.start_line,
            end_line=d.end_line,
            content=d.content,
            content_hash=d.content_hash,
        )
        for d in chunk_file(name, lines)
    )
    session.flush()
    return outcome, document.id


def _text_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if not path.is_file() or path.is_symlink():  # never follow links out of the tree
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        files.append(path)
        if len(files) >= MAX_FILES:
            break
    return files


def index_directory(
    session: Session, workspace_id: uuid.UUID, repository_id: uuid.UUID, root: Path
) -> IndexResult:
    """Index a local checkout as repository context; removes documents for vanished files."""
    root = root.resolve()
    result = IndexResult()
    seen: set[str] = set()
    for path in _text_files(root):
        name = path.relative_to(root).as_posix()
        seen.add(name)
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            result.add("skipped", None)
            continue
        outcome, document_id = upsert_document(
            session,
            workspace_id=workspace_id,
            repository_id=repository_id,
            source_type=source_type_for(name),
            name=name,
            content=content,
        )
        result.add(outcome, document_id)
    stale = session.scalars(
        select(Document).where(
            Document.repository_id == repository_id,
            Document.investigation_id.is_(None),
            Document.name.not_in(seen) if seen else Document.id.is_not(None),
        )
    ).all()
    for document in stale:
        session.delete(document)
        result.add("skipped", None)
        result.counts["removed"] = result.counts.get("removed", 0) + 1
    session.flush()
    return result


def index_knowledge(session: Session, workspace_id: uuid.UUID, root: Path) -> IndexResult:
    """Index approved knowledge notes (Markdown) as workspace-level ``kb`` documents."""
    root = root.resolve()
    result = IndexResult()
    for path in sorted(root.rglob("*.md")):
        if path.name.lower() == "readme.md" or not path.is_file():
            continue
        outcome, document_id = upsert_document(
            session,
            workspace_id=workspace_id,
            repository_id=None,
            source_type="kb",
            name=f"kb/{path.relative_to(root).as_posix()}",
            content=path.read_text(encoding="utf-8"),
        )
        result.add(outcome, document_id)
    return result


def embedding_text(document_name: str, chunk: Chunk) -> str:
    body = "\n".join(strip_timestamp(line) for line in chunk.content.split("\n"))
    label = f" ({chunk.step_name})" if chunk.step_name else ""
    return f"{document_name}{label}\n{body}"


def embed_pending(
    session: Session,
    embedder: Embedder,
    workspace_id: uuid.UUID,
    document_ids: list[uuid.UUID] | None = None,
    batch_size: int = 32,
) -> int:
    """Embed chunks that have no embedding (or one from a different model). Returns the count."""
    query = (
        select(Chunk, Document.name)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.workspace_id == workspace_id,
            (Chunk.embedding_model.is_(None)) | (Chunk.embedding_model != embedder.model),
        )
        .order_by(Chunk.document_id, Chunk.ordinal)
    )
    if document_ids is not None:
        if not document_ids:
            return 0
        query = query.where(Chunk.document_id.in_(document_ids))
    rows = session.execute(query).all()
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        vectors = embedder.embed_documents([embedding_text(name, chunk) for chunk, name in batch])
        for (chunk, _), vector in zip(batch, vectors, strict=True):
            chunk.embedding = vector
            chunk.embedding_model = embedder.model
        session.flush()
    return len(rows)
