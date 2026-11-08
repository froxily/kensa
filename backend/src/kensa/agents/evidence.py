"""Evidence as the model and the verifier see it: labelled, line-numbered excerpts."""

from dataclasses import dataclass
from uuid import UUID

from kensa.ingestion.normalize import strip_timestamp

MAX_PROMPT_LINE_CHARS = 400


@dataclass(frozen=True)
class EvidenceItem:
    label: str  # "E1", "E2", ...
    chunk_id: UUID
    document_name: str
    step_name: str | None
    start_line: int
    end_line: int
    lines: tuple[str, ...]  # timestamps stripped; index 0 is start_line
    score: float
    channels: tuple[str, ...]
    source_type: str = "log"

    def line(self, number: int) -> str | None:
        if self.start_line <= number <= self.end_line:
            return self.lines[number - self.start_line]
        return None

    def render(self) -> str:
        """The block shown to the model. Attribute values are sanitised so log text cannot
        close the tag early or fake another evidence block."""
        step = (self.step_name or "").replace('"', "'").replace("<", "(").replace(">", ")")
        name = self.document_name.replace('"', "'").replace("<", "(").replace(">", ")")
        body = "\n".join(
            f"L{self.start_line + i}: {line[:MAX_PROMPT_LINE_CHARS]}"
            for i, line in enumerate(self.lines)
        ).replace("</evidence", "&lt;/evidence")
        return (
            f'<evidence id="{self.label}" source="{self.source_type}: {name}" step="{step}" '
            f'lines="{self.start_line}-{self.end_line}">\n{body}\n</evidence>'
        )


def evidence_lines(content: str) -> tuple[str, ...]:
    return tuple(strip_timestamp(line) for line in content.split("\n"))
