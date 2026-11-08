"""Evaluation dataset loading, validation and the freeze guard.

A dataset is frozen by ``scripts/freeze_dataset.py``, which writes ``MANIFEST.sha256``: one
``<sha256>  <relative path>`` line per file. ``verify_frozen`` refuses to evaluate against a
dataset whose files differ from the manifest, so ground truth cannot drift after benchmarking
has started.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kensa.analysis.categories import CATEGORIES

MANIFEST = "MANIFEST.sha256"
SPLITS = ("dev", "test")
# v1 uses the first three; v2 (M5.1) adds causes hidden behind another tool's failure ("masked")
# and failures whose wording suggests another category ("lookalike").
KINDS = ("standard", "misleading", "insufficient", "masked", "lookalike")


class DatasetError(ValueError):
    pass


@dataclass(frozen=True)
class EvidenceRef:
    path: str  # "log" or a repository-relative path
    start_line: int
    end_line: int
    why: str


@dataclass(frozen=True)
class Case:
    id: str
    split: str
    category: str
    kind: str
    ecosystem: str
    difficulty: str
    fix_keywords: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]
    folder: Path

    @property
    def log_path(self) -> Path:
        return self.folder / "log.txt"

    @property
    def repo_path(self) -> Path:
        return self.folder / "repo"


def _require(data: dict[str, Any], key: str, kind: type, where: str) -> Any:
    value = data.get(key)
    if not isinstance(value, kind):
        raise DatasetError(f"{where}: field '{key}' missing or not {kind.__name__}")
    return value


def _lines(path: Path) -> list[str]:
    # utf-8-sig: some files were written with a byte-order mark; it is not content.
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").split("\n")


def load_case(folder: Path) -> Case:
    where = folder.name
    data = json.loads((folder / "case.json").read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise DatasetError(f"{where}: case.json is not an object")
    split = _require(data, "split", str, where)
    category = _require(data, "category", str, where)
    kind = _require(data, "kind", str, where)
    if split not in SPLITS or category not in CATEGORIES or kind not in KINDS:
        raise DatasetError(f"{where}: invalid split/category/kind {split}/{category}/{kind}")
    evidence: list[EvidenceRef] = []
    for item in _require(data, "relevant_evidence", list, where):
        path = str(item.get("path", ""))
        start, end = int(item.get("start_line", 0)), int(item.get("end_line", 0))
        file = folder / "log.txt" if path == "log" else folder / "repo" / path
        if not file.is_file() or not file.resolve().is_relative_to(folder.resolve()):
            raise DatasetError(f"{where}: evidence path not found: {path}")
        lines = _lines(file)
        if not (1 <= start <= end <= len(lines)):
            raise DatasetError(f"{where}: evidence range {start}-{end} outside {path}")
        if not any(line.strip() for line in lines[start - 1 : end]):
            raise DatasetError(f"{where}: evidence range {start}-{end} in {path} is blank")
        evidence.append(EvidenceRef(path, start, end, str(item.get("why", ""))))
    if not evidence:
        raise DatasetError(f"{where}: no relevant evidence")
    return Case(
        id=_require(data, "id", str, where),
        split=split,
        category=category,
        kind=kind,
        ecosystem=str(data.get("ecosystem", "")),
        difficulty=str(data.get("difficulty", "")),
        fix_keywords=tuple(str(k) for k in data.get("fix_keywords", [])),
        evidence=tuple(evidence),
        folder=folder,
    )


def _split_of(folder: Path) -> str | None:
    try:
        data = json.loads((folder / "case.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return data.get("split") if isinstance(data, dict) else None


def load_cases(root: Path, split: str | None = None) -> list[Case]:
    """All cases, validated; or only one split's. A split's cases are read on their own, so
    another split's files (for example a case still being written) cannot affect it. The full
    load, used by the quality gates and the freeze, still rejects any unreadable case."""
    folders = [f for f in sorted((root / "cases").iterdir()) if f.is_dir()]
    if split is not None:
        folders = [f for f in folders if _split_of(f) == split]
    return [load_case(f) for f in folders]


def _normalised_bytes(path: Path) -> bytes:
    """File content independent of line endings and a UTF-8 BOM, so the manifest holds across
    checkouts (git normalises text files to LF; editors may add CRLF or a BOM)."""
    return path.read_bytes().removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n")


def split_manifest_name(split: str) -> str:
    """A split can be frozen on its own (v2: the dev split, before the test split was written)."""
    return f"MANIFEST.{split}.sha256"


def _hash_lines(root: Path, files: list[Path]) -> list[str]:
    return [
        f"{hashlib.sha256(_normalised_bytes(p)).hexdigest()}  {p.relative_to(root).as_posix()}"
        for p in sorted(files)
    ]


def manifest_lines(root: Path) -> list[str]:
    return _hash_lines(root, [p for p in root.rglob("*") if p.is_file() and p.name != MANIFEST])


def split_manifest_lines(root: Path, split: str) -> list[str]:
    """Every file of the split's cases. Other files are frozen by the full manifest."""
    folders = [case.folder for case in load_cases(root, split)]
    return _hash_lines(root, [p for f in folders for p in f.rglob("*") if p.is_file()])


def _digest(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]


def verify_frozen(root: Path, split: str | None = None) -> str:
    """Return the manifest digest, or raise if the dataset was never frozen or has changed.

    Before the whole dataset is frozen, a split frozen on its own can be evaluated: its digest
    is returned with a ``/<split>`` suffix."""
    manifest = root / MANIFEST
    if manifest.is_file():
        expected = manifest.read_text(encoding="utf-8").strip().splitlines()
        actual = manifest_lines(root)
    elif split is not None and (root / split_manifest_name(split)).is_file():
        expected = (root / split_manifest_name(split)).read_text("utf-8").strip().splitlines()
        actual = split_manifest_lines(root, split)
        if expected == actual:
            return f"{_digest(actual)}/{split}"
    else:
        raise DatasetError("dataset is not frozen (run scripts/freeze_dataset.py)")
    if expected != actual:
        changed = sorted(set(expected) ^ set(actual))[:5]
        raise DatasetError(f"dataset differs from its frozen manifest: {changed}")
    return _digest(actual)
