"""Retrieval and diagnosis metrics. Pure functions."""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from kensa.evaluation.dataset import EvidenceRef


@dataclass(frozen=True)
class RetrievedRef:
    path: str  # "log" for the investigation's own log, else the repository path or doc name
    start_line: int
    end_line: int


def _overlaps(a: RetrievedRef, b: EvidenceRef) -> bool:
    return a.path == b.path and a.start_line <= b.end_line and b.start_line <= a.end_line


def recall_at_k(
    retrieved: Sequence[RetrievedRef], relevant: Sequence[EvidenceRef], k: int
) -> float:
    """Share of relevant evidence items overlapped by at least one of the top-k results."""
    if not relevant:
        return 0.0
    top = retrieved[:k]
    return sum(any(_overlaps(r, e) for r in top) for e in relevant) / len(relevant)


def hit_at_k(retrieved: Sequence[RetrievedRef], relevant: Sequence[EvidenceRef], k: int) -> bool:
    return any(_overlaps(r, e) for r in retrieved[:k] for e in relevant)


def reciprocal_rank(retrieved: Sequence[RetrievedRef], relevant: Sequence[EvidenceRef]) -> float:
    for rank, item in enumerate(retrieved, start=1):
        if any(_overlaps(item, e) for e in relevant):
            return 1.0 / rank
    return 0.0


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100); 0.0 for no values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(q / 100 * len(ordered) + 0.5) - 1))
    return ordered[index]


def mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0
