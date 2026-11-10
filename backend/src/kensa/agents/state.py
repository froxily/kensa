"""The agent graph's state (M3) and its conversions to the pipeline's types.

Checkpoints store this state, so it holds only plain JSON-like values (str, int, float, bool,
None, lists and dicts). LangGraph's serializer then never has to rebuild Python classes from the
database, and the checkpointer runs with its strict allowlist (DECISIONS.md D-028).
"""

import uuid
from dataclasses import asdict
from typing import Any, NotRequired, TypedDict

from kensa.agents.completeness import Completeness, LogScan
from kensa.agents.evidence import EvidenceItem
from kensa.agents.schemas import DiagnosisDraft
from kensa.agents.verifier import CheckedCitation, Verification
from kensa.analysis.classifier import RuleClassification
from kensa.analysis.signatures import SignatureMatch
from kensa.inference.base import StructuredResult

Json = dict[str, Any]


class GraphState(TypedDict):
    investigation_id: str
    workspace_id: str
    title: str
    repository_id: str | None
    channels: list[str]
    signatures: NotRequired[list[Json]]
    # v1.1 (D-054): Kensa's findings about changes since the last successful run.
    change_notes: NotRequired[list[str]]
    document_count: NotRequired[int]
    line_count: NotRequired[int]
    log_tail: NotRequired[list[str]]
    rule: NotRequired[Json]
    # M5.1: statements of an underlying cause found in the log (``kensa.analysis.causes``).
    causes: NotRequired[list[Json]]
    scan: NotRequired[Json]
    retrieval_round: NotRequired[int]
    evidence: NotRequired[list[Json]]
    completeness: NotRequired[Json]
    llm_calls: NotRequired[int]
    diagnosis_attempt: NotRequired[int]
    # The latest diagnosis attempt and its verification; ``best`` is the one reported.
    attempt: NotRequired[Json | None]
    attempts: NotRequired[list[Json]]
    best: NotRequired[Json | None]
    next_step: NotRequired[str]
    abstained: NotRequired[bool]
    proposals: NotRequired[list[Json]]
    decision: NotRequired[Json | None]


def signature_to_json(sig: SignatureMatch) -> Json:
    return asdict(sig)


def signature_from_json(data: Json) -> SignatureMatch:
    return SignatureMatch(**data)


def rule_to_json(rule: RuleClassification) -> Json:
    return {**asdict(rule), "supporting_lines": list(rule.supporting_lines)}


def rule_from_json(data: Json) -> RuleClassification:
    return RuleClassification(
        category=data["category"],
        score=data["score"],
        share=data["share"],
        scores=dict(data["scores"]),
        supporting_lines=tuple(data["supporting_lines"]),
    )


def evidence_to_json(item: EvidenceItem) -> Json:
    return {
        **asdict(item),
        "chunk_id": str(item.chunk_id),
        "lines": list(item.lines),
        "channels": list(item.channels),
    }


def evidence_from_json(data: Json) -> EvidenceItem:
    return EvidenceItem(
        **{
            **data,
            "chunk_id": uuid.UUID(data["chunk_id"]),
            "lines": tuple(data["lines"]),
            "channels": tuple(data["channels"]),
        }
    )


def scan_to_json(scan: LogScan) -> Json:
    return {
        "failure_lines": list(scan.failure_lines),
        "truncation_lines": list(scan.truncation_lines),
        "line_count": scan.line_count,
    }


def scan_from_json(data: Json) -> LogScan:
    return LogScan(
        tuple(data["failure_lines"]), tuple(data["truncation_lines"]), data["line_count"]
    )


def completeness_to_json(result: Completeness) -> Json:
    return {
        "status": result.status,
        "key_lines": list(result.key_lines),
        "missing_lines": list(result.missing_lines),
        "notes": list(result.notes),
    }


def verification_to_json(v: Verification) -> Json:
    return {
        "status": v.status,
        "category": v.category,
        "citations": [
            {**asdict(c), "chunk_id": str(c.chunk_id) if c.chunk_id else None} for c in v.citations
        ],
        "notes": list(v.notes),
        "retryable": v.retryable,
        "feedback": list(v.feedback),
    }


def verification_from_json(data: Json) -> Verification:
    return Verification(
        status=data["status"],
        category=data["category"],
        citations=[
            CheckedCitation(
                **{**c, "chunk_id": uuid.UUID(c["chunk_id"]) if c["chunk_id"] else None}
            )
            for c in data["citations"]
        ],
        notes=list(data["notes"]),
        retryable=data["retryable"],
        feedback=list(data["feedback"]),
    )


def result_to_json(result: StructuredResult[DiagnosisDraft]) -> Json:
    return {
        "draft": result.value.model_dump(mode="json"),
        "provider": result.provider,
        "model": result.model,
        "prompt_tokens": result.prompt_tokens,
        "output_tokens": result.output_tokens,
        "duration_ms": result.duration_ms,
        "attempts": result.attempts,
        "timings": dict(result.timings),
    }


def result_from_json(data: Json) -> StructuredResult[DiagnosisDraft]:
    return StructuredResult(
        value=DiagnosisDraft.model_validate(data["draft"]),
        provider=data["provider"],
        model=data["model"],
        prompt_tokens=data["prompt_tokens"],
        output_tokens=data["output_tokens"],
        duration_ms=data["duration_ms"],
        attempts=data["attempts"],
        timings=dict(data.get("timings") or {}),
    )
