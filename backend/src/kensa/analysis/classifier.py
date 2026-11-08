"""Rule-based failure classification: the deterministic baseline the LLM has to beat.

M5.1 (D-041): cause-level evidence (``kensa.analysis.causes``) counts as strong evidence for its
category, and when the log states an environmental cause, the summary lines that only report a
symptom of it (a failing test, a Docker build wrapper) count weakly. A test that fails because a
variable is missing is classified as the missing variable.
"""

from collections import defaultdict
from dataclasses import dataclass

from kensa.analysis.categories import Category
from kensa.analysis.causes import ENVIRONMENTAL, CauseEvidence
from kensa.analysis.signatures import SignatureMatch

STRONG_SCORE = 3
STRONG_SHARE = 0.6
CAUSE_WEIGHT = 3
SYMPTOM_WEIGHT = 1
# Signature rules that report that something failed, not why.
SYMPTOM_RULES = frozenset(
    {"pytest.failed", "pytest.summary", "jest.summary", "go.fail", "junit.fail", "docker.solve"}
)


@dataclass(frozen=True)
class RuleClassification:
    category: Category
    score: int
    share: float  # top category's share of all categorised weight, 0..1
    scores: dict[str, int]
    supporting_lines: tuple[int, ...]

    @property
    def is_strong(self) -> bool:
        """Strong enough that an LLM diagnosis disagreeing with it counts as contradicted."""
        return (
            self.category != "unknown" and self.score >= STRONG_SCORE and self.share >= STRONG_SHARE
        )


def classify(
    signatures: list[SignatureMatch], causes: CauseEvidence | None = None
) -> RuleClassification:
    found = causes if causes is not None else CauseEvidence()
    stated = found.categories & ENVIRONMENTAL
    scores: dict[Category, int] = defaultdict(int)
    first_line: dict[Category, int] = {}
    lines: dict[Category, set[int]] = defaultdict(set)
    for sig in signatures:
        if sig.category is None:
            continue
        weight = sig.weight
        if stated and sig.rule_id in SYMPTOM_RULES and sig.category not in stated:
            weight = SYMPTOM_WEIGHT
        scores[sig.category] += weight
        first_line[sig.category] = min(
            first_line.get(sig.category, sig.line_number), sig.line_number
        )
        lines[sig.category].add(sig.line_number)
    for cause in found.lines:
        # A line already matched by a signature of the same category is not counted twice.
        if cause.line_number not in lines[cause.category]:
            # A failing assertion is itself a symptom when an environmental cause is stated.
            symptom = stated and cause.category not in ENVIRONMENTAL
            scores[cause.category] += SYMPTOM_WEIGHT if symptom else CAUSE_WEIGHT
            lines[cause.category].add(cause.line_number)
        first_line[cause.category] = min(
            first_line.get(cause.category, cause.line_number), cause.line_number
        )

    total = sum(scores.values())
    if total == 0:
        return RuleClassification("unknown", 0, 0.0, {}, ())

    # Highest score wins; ties go to a stated environmental cause over a symptom, then to the
    # category whose evidence appears first.
    best = min(scores, key=lambda c: (-scores[c], c not in stated, first_line[c]))
    supporting = tuple(sorted(lines[best]))
    return RuleClassification(
        category=best,
        score=scores[best],
        share=scores[best] / total,
        scores=dict(sorted(scores.items(), key=lambda kv: -kv[1])),
        supporting_lines=supporting,
    )
