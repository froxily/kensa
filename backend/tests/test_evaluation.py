import json
from pathlib import Path

import pytest

from kensa.evaluation.dataset import (
    MANIFEST,
    DatasetError,
    EvidenceRef,
    load_cases,
    manifest_lines,
    split_manifest_lines,
    split_manifest_name,
    verify_frozen,
)
from kensa.evaluation.metrics import (
    RetrievedRef,
    hit_at_k,
    percentile,
    recall_at_k,
    reciprocal_rank,
)
from kensa.evaluation.v3 import freeze_split, load_history_sequences, verify_v3

RELEVANT = [
    EvidenceRef("log", 10, 12, "error"),
    EvidenceRef(".github/workflows/ci.yml", 5, 6, "env"),
]


def test_recall_mrr_and_hits() -> None:
    retrieved = [
        RetrievedRef("README.md", 1, 10),
        RetrievedRef("log", 8, 11),  # overlaps the log evidence
        RetrievedRef("log", 40, 50),
        RetrievedRef(".github/workflows/ci.yml", 7, 20),  # adjacent, not overlapping
    ]
    assert recall_at_k(retrieved, RELEVANT, 5) == 0.5
    assert recall_at_k(retrieved, RELEVANT, 1) == 0.0
    assert reciprocal_rank(retrieved, RELEVANT) == 0.5
    assert hit_at_k(retrieved, RELEVANT, 2)
    assert not hit_at_k(retrieved, RELEVANT, 1)
    assert (
        recall_at_k([*retrieved, RetrievedRef(".github/workflows/ci.yml", 1, 5)], RELEVANT, 10)
        == 1.0
    )
    assert reciprocal_rank([], RELEVANT) == 0.0


def test_percentile_nearest_rank() -> None:
    values = [10.0, 20.0, 30.0, 40.0]
    assert percentile(values, 50) == 20.0
    assert percentile(values, 95) == 40.0
    assert percentile([], 50) == 0.0


def _case(root: Path, case_id: str, evidence: list[dict[str, object]]) -> None:
    folder = root / "cases" / case_id
    (folder / "repo" / ".github" / "workflows").mkdir(parents=True)
    (folder / "log.txt").write_text("\n".join(f"line {i}" for i in range(1, 21)), encoding="utf-8")
    (folder / "repo" / ".github" / "workflows" / "ci.yml").write_text("on: push\njobs: {}\n")
    data = {
        "id": case_id,
        "split": "dev",
        "category": "docker",
        "kind": "standard",
        "relevant_evidence": evidence,
    }
    (folder / "case.json").write_text(json.dumps(data), encoding="utf-8")


def test_dataset_loads_and_validates_evidence(tmp_path: Path) -> None:
    _case(tmp_path, "c01", [{"path": "log", "start_line": 3, "end_line": 4}])
    cases = load_cases(tmp_path)
    assert [c.id for c in cases] == ["c01"]
    assert cases[0].evidence[0] == EvidenceRef("log", 3, 4, "")
    _case(tmp_path, "c02", [{"path": "log", "start_line": 19, "end_line": 25}])
    with pytest.raises(DatasetError, match="outside"):
        load_cases(tmp_path)


@pytest.mark.parametrize(
    "evidence",
    [
        [{"path": "repo/../../secret", "start_line": 1, "end_line": 1}],
        [{"path": "missing.yml", "start_line": 1, "end_line": 1}],
        [],
    ],
)
def test_bad_evidence_is_rejected(tmp_path: Path, evidence: list[dict[str, object]]) -> None:
    _case(tmp_path, "c01", evidence)
    with pytest.raises(DatasetError):
        load_cases(tmp_path)


def test_freeze_guard_detects_any_change(tmp_path: Path) -> None:
    _case(tmp_path, "c01", [{"path": "log", "start_line": 1, "end_line": 2}])
    with pytest.raises(DatasetError, match="not frozen"):
        verify_frozen(tmp_path)
    (tmp_path / MANIFEST).write_text("\n".join(manifest_lines(tmp_path)) + "\n", encoding="utf-8")
    digest = verify_frozen(tmp_path)
    assert len(digest) == 16
    (tmp_path / "cases" / "c01" / "log.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(DatasetError, match="differs"):
        verify_frozen(tmp_path)


def test_a_split_frozen_on_its_own_can_be_evaluated_until_the_whole_set_is_frozen(
    tmp_path: Path,
) -> None:
    # M5.1: v2's dev split was frozen before its test split was written.
    _case(tmp_path, "d01", [{"path": "log", "start_line": 1, "end_line": 2}])
    (tmp_path / split_manifest_name("dev")).write_text(
        "\n".join(split_manifest_lines(tmp_path, "dev")) + "\n", encoding="utf-8"
    )
    assert verify_frozen(tmp_path, "dev").endswith("/dev")
    with pytest.raises(DatasetError, match="not frozen"):
        verify_frozen(tmp_path, "test")  # a split without its own manifest
    with pytest.raises(DatasetError, match="not frozen"):
        verify_frozen(tmp_path)  # the whole set is not frozen yet
    log = tmp_path / "cases" / "d01" / "log.txt"
    log.write_text(log.read_text(encoding="utf-8") + "\ntampered", encoding="utf-8")
    with pytest.raises(DatasetError, match="differs"):
        verify_frozen(tmp_path, "dev")


# ------------------------------------------------------------------------------ v3 (v1.1) ---


def _v3_history(root: Path) -> None:
    for name, split in (("hd01-x", "dev"), ("ht01-y", "test")):
        folder = root / "sequences" / name
        folder.mkdir(parents=True)
        entries = [
            {
                "id": f"e{i}",
                "file": f"e{i}.log",
                "cluster": c,
                "relation": r,
                "category": "missing_env_var",
            }
            for i, (c, r) in enumerate((("a", "first"), ("a", "recurrence")), start=1)
        ]
        (folder / "sequence.json").write_text(
            json.dumps({"id": name, "split": split, "entries": entries}), encoding="utf-8"
        )
        for entry in entries:
            (folder / entry["file"]).write_text("Error: KEY is not set\n", encoding="utf-8")


def test_a_v3_history_split_is_frozen_on_its_own_and_any_change_is_refused(
    tmp_path: Path,
) -> None:
    _v3_history(tmp_path)
    (dev,) = load_history_sequences(tmp_path, "dev")
    assert [e.cluster for e in dev.entries] == ["hd01-x:a", "hd01-x:a"]
    with pytest.raises(DatasetError, match="not frozen"):
        verify_v3(tmp_path, "dev")
    digest = freeze_split(tmp_path, "dev")
    assert verify_v3(tmp_path, "dev") == digest
    # The test split is not part of the dev manifest, so writing it does not unfreeze dev...
    (tmp_path / "sequences" / "ht01-y" / "e2.log").write_text("other\n", encoding="utf-8")
    assert verify_v3(tmp_path, "dev") == digest
    # ...but any change to a dev file is refused.
    (tmp_path / "sequences" / "hd01-x" / "e2.log").write_text("edited\n", encoding="utf-8")
    with pytest.raises(DatasetError, match="differs"):
        verify_v3(tmp_path, "dev")


def test_a_v3_history_sequence_with_an_unknown_relation_is_refused(tmp_path: Path) -> None:
    _v3_history(tmp_path)
    path = tmp_path / "sequences" / "hd01-x" / "sequence.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["entries"][1]["relation"] = "cousin"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DatasetError, match="unknown relation"):
        load_history_sequences(tmp_path, "dev")
