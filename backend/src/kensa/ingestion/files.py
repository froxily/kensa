"""Chunking for repository files and knowledge notes (M2): workflow YAML by job/step, Markdown by
heading, code by top-level definition, anything else by fixed windows.

Every chunk keeps exact 1-based line ranges, so citations into these files stay verifiable.
"""

import re
from pathlib import PurePosixPath

import yaml

from kensa.ingestion.chunking import ChunkDraft

WINDOW = 60
_CODE_BOUNDARY = {
    ".py": re.compile(r"^(?:async\s+def|def|class)\s+\w+"),
    ".js": re.compile(
        r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class)\b|^(?:export\s+)?const\s+\w+\s*="
    ),
    ".go": re.compile(r"^(?:func|type)\s"),
    ".rs": re.compile(r"^(?:pub\s+)?(?:async\s+)?(?:fn|struct|enum|impl|mod)\b"),
}
_CODE_BOUNDARY[".ts"] = _CODE_BOUNDARY[".tsx"] = _CODE_BOUNDARY[".jsx"] = _CODE_BOUNDARY[".js"]
_HEADING = re.compile(r"^#{1,6}\s")


def source_type_for(path: str) -> str:
    """Document source type for a repository-relative path."""
    pure = PurePosixPath(path.replace("\\", "/"))
    parts = [p.lower() for p in pure.parts]
    if len(parts) >= 3 and parts[0] == ".github" and parts[1] == "workflows":
        return "workflow_yaml"
    if pure.suffix.lower() in {".md", ".markdown", ".rst"}:
        return "doc"
    return "code"


def _windows(
    lines: list[str], start: int, end: int, label: str | None, kind: str
) -> list[tuple[str, str | None, int, int]]:
    return [(kind, label, s, min(end, s + WINDOW - 1)) for s in range(start, end + 1, WINDOW)]


def _trim(lines: list[str], start: int, end: int) -> tuple[int, int]:
    while end > start and not lines[end - 1].strip():
        end -= 1
    return start, end


def _yaml_spans(lines: list[str]) -> list[tuple[str, str | None, int, int]]:
    """Workflow header (everything before ``jobs:``), then one span per job, split per step
    when a job is longer than the window."""
    node = yaml.compose("\n".join(lines))
    if not isinstance(node, yaml.MappingNode):
        raise ValueError("not a mapping")

    # PyYAML end marks point at the *next* token, so spans end on the line before the next
    # sibling starts (or at the end of the enclosing block), never on mark arithmetic.
    top_keys = [k for k, _ in node.value]
    spans: list[tuple[str, str | None, int, int]] = []
    jobs_index = next(
        (i for i, k in enumerate(top_keys) if getattr(k, "value", None) == "jobs"), None
    )
    if jobs_index is None or not isinstance(node.value[jobs_index][1], yaml.MappingNode):
        return _windows(lines, 1, len(lines), None, "workflow")
    jobs_key, jobs_value = node.value[jobs_index]
    if jobs_key.start_mark.line > 0:
        spans.append(("workflow", "workflow settings", *_trim(lines, 1, jobs_key.start_mark.line)))
    jobs_end = (
        top_keys[jobs_index + 1].start_mark.line if jobs_index + 1 < len(top_keys) else len(lines)
    )
    jobs = jobs_value.value
    for job_index, (job_key, job_value) in enumerate(jobs):
        next_start = (
            jobs[job_index + 1][0].start_mark.line if job_index + 1 < len(jobs) else jobs_end
        )
        start, end = _trim(
            lines, job_key.start_mark.line + 1, max(next_start, job_key.start_mark.line + 1)
        )
        name = f"job {job_key.value}"
        if end - start + 1 <= WINDOW or not isinstance(job_value, yaml.MappingNode):
            spans.append(("job", name, start, end))
            continue
        steps = next((v for k, v in job_value.value if getattr(k, "value", None) == "steps"), None)
        if not isinstance(steps, yaml.SequenceNode) or not steps.value:
            spans += _windows(lines, start, end, name, "job")
            continue
        spans.append(("job", name, start, steps.value[0].start_mark.line))
        for index, step in enumerate(steps.value):
            s0 = step.start_mark.line + 1
            nxt = steps.value[index + 1].start_mark.line if index + 1 < len(steps.value) else end
            s_start, s_end = _trim(lines, s0, max(s0, nxt))
            spans.append(("step", f"{name} step {index + 1}", s_start, min(s_end, end)))
    return spans


def _boundary_spans(
    lines: list[str], boundary: re.Pattern[str], kind: str
) -> list[tuple[str, str | None, int, int]]:
    starts = [i + 1 for i, line in enumerate(lines) if boundary.match(line)]
    if not starts or starts[0] != 1:
        starts = [1, *starts]
    spans: list[tuple[str, str | None, int, int]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] - 1 if index + 1 < len(starts) else len(lines)
        start, end = _trim(lines, start, end)
        label = lines[start - 1].strip()[:120] or None
        spans += _windows(lines, start, end, label, kind)
    return spans


def _markdown_spans(lines: list[str]) -> list[tuple[str, str | None, int, int]]:
    in_fence = False
    starts: list[int] = []
    for i, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and _HEADING.match(line):
            starts.append(i)
    if not starts or starts[0] != 1:
        starts = [1, *starts]
    spans: list[tuple[str, str | None, int, int]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] - 1 if index + 1 < len(starts) else len(lines)
        start, end = _trim(lines, start, end)
        label = lines[start - 1].lstrip("# ").strip()[:120] or None
        spans += _windows(lines, start, end, label, "section")
    return spans


def chunk_file(path: str, lines: list[str]) -> list[ChunkDraft]:
    if not lines:
        return []
    source_type = source_type_for(path)
    suffix = PurePosixPath(path).suffix.lower()
    spans: list[tuple[str, str | None, int, int]]
    if source_type == "workflow_yaml":
        try:
            spans = _yaml_spans(lines)
        except (yaml.YAMLError, ValueError):
            spans = _windows(lines, 1, len(lines), None, "workflow")
    elif source_type == "doc":
        spans = _markdown_spans(lines)
    elif suffix in _CODE_BOUNDARY:
        spans = _boundary_spans(lines, _CODE_BOUNDARY[suffix], "code")
    else:
        spans = _windows(lines, 1, len(lines), None, "code")

    drafts: list[ChunkDraft] = []
    for kind, label, start, end in spans:
        if start > end or not any(line.strip() for line in lines[start - 1 : end]):
            continue
        content = "\n".join(lines[start - 1 : end])
        drafts.append(ChunkDraft(len(drafts), kind, label, start, end, content))
    return drafts
