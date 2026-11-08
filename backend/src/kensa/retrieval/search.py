"""Evidence retrieval for one investigation.

Scope (workspace-filtered): the investigation's own logs, the files of its repository (if any),
and workspace knowledge: kb notes and past incidents, never the investigation's own incident.

Channels:
* ``signature``: chunks holding deterministic error-signature lines, ranked by summed weight;
* ``fts``: PostgreSQL full-text search (``simple`` config) for terms taken from the signatures;
* ``vector``: pgvector cosine similarity to an embedded query (M2);
* ``tail``: the last chunks of the log, used only when the other channels find nothing.

Rankings are merged with Reciprocal Rank Fusion using weights fixed before evaluation
(DECISIONS.md D-023). Excerpts that mostly overlap an already selected excerpt of the same
document are dropped, so the model's context is not spent on the same lines twice.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from kensa.analysis.signatures import SignatureMatch
from kensa.db.models import Chunk, Document
from kensa.ingestion.normalize import strip_timestamp

RRF_K = 60
CHANNEL_WEIGHTS = {"signature": 1.0, "fts": 0.8, "vector": 0.8, "tail": 0.5}
ALL_CHANNELS = frozenset({"signature", "fts", "vector"})
CANDIDATES_PER_CHANNEL = 20
MAX_TERMS = 30
_TERM = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,40}")
_STOPWORDS = frozenset(
    (
        "the and for with that this from was were are not but you your have has had into run "
        "error errors process completed exit code line file see more info npm"
    ).split()
)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    source_type: str
    kind: str
    step_name: str | None
    start_line: int
    end_line: int
    content: str
    score: float
    channels: tuple[str, ...]


def query_terms(signatures: Sequence[SignatureMatch]) -> list[str]:
    """Distinctive tokens from signature values and excerpts, strongest signatures first."""
    terms: list[str] = []
    for sig in sorted(signatures, key=lambda s: (-s.weight, s.line_number)):
        for token in _TERM.findall(f"{sig.value} {sig.excerpt}"):
            lowered = token.lower()
            if lowered not in _STOPWORDS and lowered not in terms:
                terms.append(lowered)
            if len(terms) >= MAX_TERMS:
                return terms
    return terms


def vector_query_text(title: str, signatures: Sequence[SignatureMatch], tail: Sequence[str]) -> str:
    """What the failure looks like, for the embedding query: title plus the strongest error
    lines, or the end of the log when no signature matched."""
    strongest = sorted(signatures, key=lambda s: (-s.weight, s.line_number))[:6]
    lines = [s.excerpt for s in strongest] or [strip_timestamp(t) for t in tail[-20:]]
    return "\n".join([title, *lines])[:3000]


def rrf(rankings: dict[str, list[uuid.UUID]]) -> list[tuple[uuid.UUID, float, tuple[str, ...]]]:
    scores: dict[uuid.UUID, float] = {}
    channels: dict[uuid.UUID, list[str]] = {}
    for channel, ranked in rankings.items():
        weight = CHANNEL_WEIGHTS.get(channel, 1.0)
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (RRF_K + rank)
            channels.setdefault(chunk_id, []).append(channel)
    ordered = sorted(scores, key=lambda c: -scores[c])
    return [(c, scores[c], tuple(channels[c])) for c in ordered]


# The FTS and vector channels share one scope predicate, written out in full in each literal
# statement: own logs, the repository's files, workspace kb notes and other incidents.
_SIGNATURE_CHANNEL = text(
    """
    SELECT es.chunk_id
    FROM error_signatures es
    JOIN documents d ON d.id = es.document_id
    WHERE d.investigation_id = :investigation_id AND es.workspace_id = :workspace_id
      AND es.chunk_id IS NOT NULL
    GROUP BY es.chunk_id
    ORDER BY sum(es.weight) DESC, min(es.line_number) ASC
    LIMIT :limit
    """
)
_FTS_CHANNEL = text(
    """
    SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE c.workspace_id = :workspace_id AND (
            d.investigation_id = :investigation_id
            OR (d.investigation_id IS NULL AND d.repository_id = :repository_id)
            OR (d.investigation_id IS NULL AND d.repository_id IS NULL
                AND d.source_type IN ('kb', 'incident') AND d.name NOT IN (
                    -- No self-confirmation (D-026): neither this investigation's incident nor
                    -- that of any investigation of the same log is evidence.
                    SELECT 'incident/' || other.investigation_id::text
                    FROM documents other
                    JOIN documents mine ON mine.content_hash = other.content_hash
                    WHERE mine.investigation_id = :investigation_id
                      AND mine.source_type = 'log' AND other.source_type = 'log'
                      AND other.workspace_id = :workspace_id
                      AND other.investigation_id IS NOT NULL
                ))
        )
      AND c.tsv @@ to_tsquery('simple', :query)
    ORDER BY ts_rank_cd(c.tsv, to_tsquery('simple', :query)) DESC, c.start_line ASC
    LIMIT :limit
    """
)
_VECTOR_CHANNEL = text(
    """
    SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE c.workspace_id = :workspace_id AND (
            d.investigation_id = :investigation_id
            OR (d.investigation_id IS NULL AND d.repository_id = :repository_id)
            OR (d.investigation_id IS NULL AND d.repository_id IS NULL
                AND d.source_type IN ('kb', 'incident') AND d.name NOT IN (
                    -- No self-confirmation (D-026): neither this investigation's incident nor
                    -- that of any investigation of the same log is evidence.
                    SELECT 'incident/' || other.investigation_id::text
                    FROM documents other
                    JOIN documents mine ON mine.content_hash = other.content_hash
                    WHERE mine.investigation_id = :investigation_id
                      AND mine.source_type = 'log' AND other.source_type = 'log'
                      AND other.workspace_id = :workspace_id
                      AND other.investigation_id IS NOT NULL
                ))
        )
      AND c.embedding IS NOT NULL
    ORDER BY c.embedding <=> CAST(:vector AS vector)
    LIMIT :limit
    """
)
_TAIL_CHANNEL = text(
    """
    SELECT c.id
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE d.investigation_id = :investigation_id AND c.workspace_id = :workspace_id
      AND c.kind = 'step'
    ORDER BY c.end_line DESC
    LIMIT 3
    """
)


def _overlap(a: RetrievedChunk, b: RetrievedChunk) -> float:
    if a.document_id != b.document_id:
        return 0.0
    shared = min(a.end_line, b.end_line) - max(a.start_line, b.start_line) + 1
    return max(0, shared) / (a.end_line - a.start_line + 1)


def channel_rankings(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    investigation_id: uuid.UUID,
    repository_id: uuid.UUID | None,
    signatures: Sequence[SignatureMatch],
    query_vector: Sequence[float] | None,
    channels: frozenset[str] = ALL_CHANNELS,
) -> dict[str, list[uuid.UUID]]:
    params = {
        "investigation_id": investigation_id,
        "workspace_id": workspace_id,
        "repository_id": repository_id,
        "limit": CANDIDATES_PER_CHANNEL,
    }
    rankings: dict[str, list[uuid.UUID]] = {}
    if "signature" in channels:
        rankings["signature"] = list(session.scalars(_SIGNATURE_CHANNEL, params))
    terms = query_terms(signatures)
    if "fts" in channels and terms:
        # Terms match _TERM, so they are safe tsquery lexemes; OR them together.
        query = {**params, "query": " | ".join(terms)}
        rankings["fts"] = list(session.scalars(_FTS_CHANNEL, query))
    if "vector" in channels and query_vector is not None:
        # Iterative HNSW scans keep returning candidates when the scope filter removes many.
        session.execute(text("SET LOCAL hnsw.ef_search = 200"))
        session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        literal = "[" + ",".join(f"{v:.7f}" for v in query_vector) + "]"
        rankings["vector"] = list(session.scalars(_VECTOR_CHANNEL, {**params, "vector": literal}))
    if not any(rankings.values()):
        rankings["tail"] = list(session.scalars(_TAIL_CHANNEL, params))
    return rankings


def retrieve(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    investigation_id: uuid.UUID,
    signatures: Sequence[SignatureMatch],
    repository_id: uuid.UUID | None = None,
    query_vector: Sequence[float] | None = None,
    channels: frozenset[str] = ALL_CHANNELS,
    max_chunks: int = 8,
) -> list[RetrievedChunk]:
    rankings = channel_rankings(
        session,
        workspace_id=workspace_id,
        investigation_id=investigation_id,
        repository_id=repository_id,
        signatures=signatures,
        query_vector=query_vector,
        channels=channels,
    )
    fused = rrf(rankings)
    if not fused:
        return []
    rows = session.execute(
        select(Chunk, Document.name, Document.source_type)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.id.in_([c for c, _, _ in fused]), Chunk.workspace_id == workspace_id)
    ).all()
    by_id = {chunk.id: (chunk, name, source_type) for chunk, name, source_type in rows}

    selected: list[RetrievedChunk] = []
    for chunk_id, score, found_by in fused:
        if chunk_id not in by_id:
            continue
        chunk, name, source_type = by_id[chunk_id]
        candidate = RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_name=name,
            source_type=source_type,
            kind=chunk.kind,
            step_name=chunk.step_name,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            content=chunk.content,
            score=score,
            channels=found_by,
        )
        if any(_overlap(candidate, kept) > 0.5 for kept in selected):
            continue
        selected.append(candidate)
        if len(selected) >= max_chunks:
            break
    return selected
