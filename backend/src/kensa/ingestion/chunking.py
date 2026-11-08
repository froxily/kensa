"""CI-log-aware chunking.

Two kinds of chunk cover a log:
* ``step``: a GitHub Actions step (``##[group]`` … next group), split into windows of at most
  ``STEP_WINDOW`` lines;
* ``error_window``: a few lines around each error signature, merged when they overlap. These are
  the high-value chunks that retrieval and citations mostly point at.
"""

import hashlib
from dataclasses import dataclass

from kensa.ingestion.normalize import strip_timestamp

STEP_WINDOW = 60
ERROR_BEFORE = 6
ERROR_AFTER = 3
MAX_ERROR_WINDOW = 40
PREAMBLE = "(setup)"
_GROUP = "##[group]"


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    kind: str
    step_name: str | None
    start_line: int
    end_line: int
    content: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def _steps(lines: list[str]) -> list[tuple[str, int, int]]:
    """(name, first line, last line) for each step; 1-based, inclusive."""
    steps: list[tuple[str, int, int]] = []
    name, start = PREAMBLE, 1
    for number, line in enumerate(lines, start=1):
        body = strip_timestamp(line)
        if body.startswith(_GROUP):
            if number > start:
                steps.append((name, start, number - 1))
            name, start = (body[len(_GROUP) :].strip() or "(unnamed step)")[:300], number
    if start <= len(lines):
        steps.append((name, start, len(lines)))
    return steps


def _error_windows(line_count: int, signature_lines: list[int]) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    for line in sorted(set(signature_lines)):
        start, end = max(1, line - ERROR_BEFORE), min(line_count, line + ERROR_AFTER)
        if windows and start <= windows[-1][1] + 1:
            merged = (windows[-1][0], max(windows[-1][1], end))
            if merged[1] - merged[0] + 1 <= MAX_ERROR_WINDOW:
                windows[-1] = merged
                continue
            start = windows[-1][1] + 1
        if start <= end:
            windows.append((start, end))
    return windows


def chunk_log(lines: list[str], signature_lines: list[int]) -> list[ChunkDraft]:
    steps = _steps(lines)

    def step_of(line: int) -> str | None:
        for name, start, end in steps:
            if start <= line <= end:
                return name
        return None

    def text(start: int, end: int) -> str:
        return "\n".join(lines[start - 1 : end])

    drafts: list[ChunkDraft] = []
    for name, start, end in steps:
        for window_start in range(start, end + 1, STEP_WINDOW):
            window_end = min(end, window_start + STEP_WINDOW - 1)
            drafts.append(
                ChunkDraft(
                    len(drafts),
                    "step",
                    name,
                    window_start,
                    window_end,
                    text(window_start, window_end),
                )
            )
    for start, end in _error_windows(len(lines), signature_lines):
        drafts.append(
            ChunkDraft(len(drafts), "error_window", step_of(start), start, end, text(start, end))
        )
    return drafts
