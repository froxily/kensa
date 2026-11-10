"""Evaluation sets v3 (v1.1): ``v3-change`` (change-aware investigation) and ``v3-history``
(fingerprints and similar failures). Loading and validation only; the gates are in
``scripts/freeze_v3.py`` and the evaluation in ``scripts/evaluate_v3.py``.

Both sets are frozen like v1 and v2 (``MANIFEST.<split>.sha256`` per split, then
``MANIFEST.sha256``), and ``verify_v3`` refuses to evaluate a changed split.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kensa.analysis.categories import CATEGORIES
from kensa.db.models import CHANGE_COMPARABILITY, CHANGE_KINDS
from kensa.evaluation.dataset import (
    MANIFEST,
    DatasetError,
    EvidenceRef,
    _digest,
    _hash_lines,
    manifest_lines,
)

SPLITS = ("dev", "test")
CULPRIT_KINDS = (*CHANGE_KINDS, "none")
UNVERIFIED = (
    "baseline_log_unavailable",
    "runner_labels_unknown",
    "runner_image_unknown",
    "runner_image_changed",
    "history_diverged",
)
RELATIONS = ("first", "recurrence", "lookalike")
RUNNER_IMAGE = "<runner-image>"


@dataclass(frozen=True)
class ChangeCase:
    id: str
    split: str
    comparability: str
    category: str
    culprit_kind: str
    culprit_paths: tuple[str, ...]
    culprit_commit: str | None
    unverified: tuple[str, ...]
    relevant_evidence: tuple[EvidenceRef, ...]
    folder: Path


@dataclass(frozen=True)
class HistoryEntry:
    id: str
    file: str
    cluster: str
    relation: str
    category: str
    path: Path


@dataclass(frozen=True)
class HistorySequence:
    id: str
    split: str
    entries: tuple[HistoryEntry, ...]
    folder: Path


def _split_of(case_id: str) -> str:
    prefix = case_id.split("-", 1)[0]
    return "test" if prefix.startswith(("t", "ht")) else "dev"


def _require(data: dict[str, Any], key: str, where: str) -> Any:
    if key not in data:
        raise DatasetError(f"{where}: missing {key}")
    return data[key]


def load_change_case(folder: Path) -> ChangeCase:
    where = folder.name
    data = json.loads((folder / "case.json").read_text(encoding="utf-8-sig"))
    comparability = _require(data, "comparability", where)
    category = _require(data, "category", where)
    kind = _require(data, "culprit_kind", where)
    if comparability not in CHANGE_COMPARABILITY:
        raise DatasetError(f"{where}: unknown comparability {comparability!r}")
    if category not in CATEGORIES:
        raise DatasetError(f"{where}: unknown category {category!r}")
    if kind not in CULPRIT_KINDS:
        raise DatasetError(f"{where}: unknown culprit_kind {kind!r}")
    unverified = tuple(data.get("unverified_factors") or ())
    if any(u not in UNVERIFIED for u in unverified):
        raise DatasetError(f"{where}: unknown unverified factor in {unverified}")
    evidence = tuple(
        EvidenceRef(
            path=str(e["path"]),
            start_line=int(e["start_line"]),
            end_line=int(e["end_line"]),
            why=str(e.get("why", "")),
        )
        for e in data.get("relevant_evidence") or []
    )
    return ChangeCase(
        id=str(_require(data, "id", where)),
        split=str(_require(data, "split", where)),
        comparability=comparability,
        category=category,
        culprit_kind=kind,
        culprit_paths=tuple(str(p) for p in data.get("culprit_paths") or ()),
        culprit_commit=data.get("culprit_commit"),
        unverified=unverified,
        relevant_evidence=evidence,
        folder=folder,
    )


def load_change_cases(root: Path, split: str | None = None) -> list[ChangeCase]:
    cases = [
        load_change_case(folder)
        for folder in sorted((root / "cases").iterdir())
        if folder.is_dir() and (folder / "case.json").is_file()
    ]
    return [c for c in cases if split is None or c.split == split]


def load_history_sequence(folder: Path) -> HistorySequence:
    where = folder.name
    data = json.loads((folder / "sequence.json").read_text(encoding="utf-8-sig"))
    entries = []
    for item in _require(data, "entries", where):
        relation = str(item.get("relation"))
        if relation not in RELATIONS:
            raise DatasetError(f"{where}: unknown relation {relation!r}")
        category = str(item.get("category"))
        if category not in CATEGORIES:
            raise DatasetError(f"{where}: unknown category {category!r}")
        entries.append(
            HistoryEntry(
                id=str(item["id"]),
                file=str(item["file"]),
                cluster=f"{data['id']}:{item['cluster']}",
                relation=relation,
                category=category,
                path=folder / str(item["file"]),
            )
        )
    return HistorySequence(
        id=str(_require(data, "id", where)),
        split=str(_require(data, "split", where)),
        entries=tuple(entries),
        folder=folder,
    )


def load_history_sequences(root: Path, split: str | None = None) -> list[HistorySequence]:
    sequences = [
        load_history_sequence(folder)
        for folder in sorted((root / "sequences").iterdir())
        if folder.is_dir() and (folder / "sequence.json").is_file()
    ]
    return [s for s in sequences if split is None or s.split == split]


# ------------------------------------------------------------------------------ freezing ---


def _items_dir(root: Path) -> Path:
    return root / ("cases" if (root / "cases").is_dir() else "sequences")


def split_folders(root: Path, split: str) -> list[Path]:
    return [
        f for f in sorted(_items_dir(root).iterdir()) if f.is_dir() and _split_of(f.name) == split
    ]


def split_lines(root: Path, split: str) -> list[str]:
    folders = split_folders(root, split)
    return _hash_lines(root, [p for f in folders for p in f.rglob("*") if p.is_file()])


def freeze_split(root: Path, split: str) -> str:
    lines = split_lines(root, split)
    (root / f"MANIFEST.{split}.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"{_digest(lines)}/{split}"


def freeze_all(root: Path) -> str:
    lines = manifest_lines(root)
    (root / MANIFEST).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return _digest(lines)


def verify_v3(root: Path, split: str) -> str:
    """The split's digest, or ``DatasetError`` if it was never frozen or has changed."""
    manifest = root / f"MANIFEST.{split}.sha256"
    if not manifest.is_file():
        raise DatasetError(f"{root.name} {split} split is not frozen")
    expected = manifest.read_text(encoding="utf-8").strip().splitlines()
    actual = split_lines(root, split)
    if expected != actual:
        changed = sorted(set(expected) ^ set(actual))[:5]
        raise DatasetError(f"{root.name} {split} differs from its frozen manifest: {changed}")
    return f"{_digest(actual)}/{split}"
