"""Normalisation of untrusted log text, before anything else reads it.

Line numbers are defined on the normalised text; every later step (redaction, chunking,
citations) must keep the line count unchanged.
"""

import re
from dataclasses import dataclass

MAX_LOG_BYTES = 2_000_000
MAX_LINES = 50_000
MAX_LINE_CHARS = 2_000
TRUNCATION_MARK = " …[truncated]"

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z ?")


class LogRejectedError(ValueError):
    """The input cannot be ingested (too large, too many lines, or empty)."""


@dataclass(frozen=True)
class NormalizedLog:
    text: str
    line_count: int
    truncated_lines: int


def normalize_log(raw: str) -> NormalizedLog:
    if len(raw.encode("utf-8", "replace")) > MAX_LOG_BYTES:
        raise LogRejectedError(f"log exceeds {MAX_LOG_BYTES} bytes")
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", _ANSI.sub("", text))
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) > MAX_LINES:
        raise LogRejectedError(f"log exceeds {MAX_LINES} lines")
    if not any(line.strip() for line in lines):
        raise LogRejectedError("log is empty")

    truncated = 0
    out: list[str] = []
    for line in lines:
        line = line.rstrip()
        if len(line) > MAX_LINE_CHARS:
            line = line[:MAX_LINE_CHARS] + TRUNCATION_MARK
            truncated += 1
        out.append(line)
    return NormalizedLog(text="\n".join(out), line_count=len(out), truncated_lines=truncated)


def strip_timestamp(line: str) -> str:
    """Drop the ``2026-10-01T10:00:00.1234567Z`` prefix GitHub Actions adds to every line."""
    return _TIMESTAMP.sub("", line, count=1)
