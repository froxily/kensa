"""Record the replay demo (M6): real runs of Kensa, saved for the static replay build.

    uv run --directory backend --no-sync python ../scripts/record_replays.py
    uv run --directory backend --no-sync python ../scripts/record_replays.py --verify

Needs the Compose database and Ollama with the models named in .env. It:

1. prepares a dedicated ``kensa_replay`` database (created, migrated and emptied, like the
   end-to-end server) and indexes the knowledge notes, as the evaluation harness does;
2. starts the real app on 127.0.0.1:8020, in this process, in its production settings: the agent
   graph, hybrid retrieval and the local model;
3. investigates the three built-in samples through the HTTP API, then three dev-split cases of
   evaluation set v2 together with their repository files (the evaluation harness's path, through
   the same service the API uses), then one dev-split case of the synthetic v3-change set with its
   change analysis (format 2, v1.1; the replay labels it synthetic). Test splits are never read;
4. saves every response the UI needs to ``frontend/replay/recording.json``, with a manifest
   (recording time, commit, model, GPU): each run, its timeline, documents, similar failures and
   changes, and the analytics dashboard. No decision is recorded.

Every string in the recording is checked with ``security_scan.py``'s patterns and for local
paths; on any finding nothing is written. Logs and model output are stored as data, never executed.

``--verify`` changes nothing and needs no model: it serves the runs stored in ``kensa_replay``
(no worker, mock provider) and checks that the committed recording is exactly what the API
returns for them. ``backend/tests/test_replay_recording.py`` checks the recording against the
source files.
"""

import json
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Any

import httpx
import uvicorn
from benchmark_model import git_sha, gpu_description
from e2e_server import prepare_database
from pydantic import SecretStr
from security_scan import findings
from sqlalchemy import Engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from kensa.app import create_app
from kensa.changes.analyzer import analyze
from kensa.changes.service import failure_subjects
from kensa.changes.sources import FixtureChangeSource
from kensa.changes.store import save_analysis
from kensa.core.config import Settings
from kensa.db.models import DEFAULT_WORKSPACE_ID
from kensa.db.session import build_engine
from kensa.evaluation.dataset import load_cases
from kensa.indexing.service import (
    embed_pending,
    ensure_repository,
    index_directory,
    index_knowledge,
)
from kensa.inference.embeddings import Embedder
from kensa.inference.factory import embedder_for
from kensa.investigations.service import NewInvestigation, create_investigation

REPO_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = REPO_ROOT / "knowledge"
DATASET = REPO_ROOT / "eval" / "datasets" / "v2"
OUTPUT = REPO_ROOT / "frontend" / "replay" / "recording.json"
DATABASE = "kensa_replay"
PORT = 8020
API = f"http://127.0.0.1:{PORT}"
TERMINAL = {"awaiting_approval", "completed", "failed"}
RUN_TIMEOUT_S = 900

# Dev-split cases that show the honest side of Kensa (see eval/reports/m52-v2-dev.jsonl, where
# every model configuration agreed on them): a cause stated behind a failing test, a test
# regression that stays a hypothesis (with a repository diff to review), and a log that does
# not show the failure, so Kensa abstains.
DEV_CASES = ("d45-coast-scope", "d03-tide-rounding", "d33-plum-cutoff")
# One synthetic v3-change dev case (validated, frozen) shows the change-aware panel (v1.1).
CHANGE_CASE = "d10-saffron-compose"
CHANGE_DATASET = REPO_ROOT / "eval" / "datasets" / "v3-change"

# This machine's own paths would reveal the recording user's name or folder layout. CI logs are
# full of runner paths such as /home/runner/work/...; those are log content, not local paths.
# So a GitHub-hosted runner's home is never one: it reveals nothing about anyone, and on a runner
# (where the tests run in CI) it would flag the recorded logs themselves.
RUNNER_HOME = "/home/runner"


def local_paths(*paths: PurePath) -> tuple[str, ...]:
    """Lower-cased spellings of the given paths, leaving out a CI runner's home."""
    variants = {variant.lower() for path in paths for variant in (str(path), path.as_posix())}
    return tuple(
        sorted(
            variant
            for variant in variants
            if variant != RUNNER_HOME and not variant.startswith(f"{RUNNER_HOME}/")
        )
    )


LOCAL_PATHS = local_paths(Path.home(), REPO_ROOT)


def strings_in(value: Any, where: str = "$") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield where, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from strings_in(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from strings_in(item, f"{where}[{index}]")


def check_recording(recording: dict[str, Any], paths: tuple[str, ...] = LOCAL_PATHS) -> list[str]:
    """Return one line per string that must not be published (empty when the recording is safe)."""
    problems: list[str] = []
    for where, text in strings_in(recording):
        found = findings(text)
        if any(path in text.lower() for path in paths):
            found.append("local path")
        problems.extend(f"{where}: {kind}" for kind in found)
    return problems


def wait_for(client: httpx.Client, investigation_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + RUN_TIMEOUT_S
    while time.monotonic() < deadline:
        detail: dict[str, Any] = client.get(f"/api/investigations/{investigation_id}").json()
        if detail["status"] in TERMINAL:
            print(f"  {detail['title'][:60]}: {detail['status']}, {detail['category']}", flush=True)
            return detail
        time.sleep(2)
    raise TimeoutError(f"investigation {investigation_id} did not finish in {RUN_TIMEOUT_S} s")


def export(client: httpx.Client, ids: list[str], settings: Settings) -> dict[str, Any]:
    investigations, events, documents = [], {}, {}
    history: dict[str, Any] = {}
    changes: dict[str, Any] = {}
    for investigation_id in ids:
        detail = client.get(f"/api/investigations/{investigation_id}").json()
        investigations.append(detail)
        events[investigation_id] = client.get(
            f"/api/investigations/{investigation_id}/events"
        ).json()
        for document in detail["documents"]:
            path = f"/api/investigations/{investigation_id}/documents/{document['id']}"
            documents[f"{investigation_id}/{document['id']}"] = client.get(path).json()
        history[investigation_id] = client.get(
            f"/api/investigations/{investigation_id}/history"
        ).json()
        changes[investigation_id] = client.get(
            f"/api/investigations/{investigation_id}/changes"
        ).json()
    status = ["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--untracked-files=no"]
    dirty = subprocess.run(  # noqa: S603  (fixed argv built in this file)
        status,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return {
        "format": 2,
        "manifest": {
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "commit": git_sha() + ("-dirty" if dirty else ""),
            "model": settings.llm_model,
            "num_ctx": settings.llm_num_ctx,
            "embedding_model": settings.embedding_model,
            "gpu": gpu_description(),
            "configuration": "agent graph, hybrid retrieval, local model (production settings)",
        },
        "investigations": investigations,
        "events": events,
        "documents": documents,
        "samples": client.get("/api/samples").json(),
        "history": history,
        "changes": changes,
        "repositories": client.get("/api/history/repositories").json(),
        # Every recorded run is a sample or an evaluation case, so all origins are included.
        "analytics": client.get(
            "/api/analytics/dashboard", params={"days": 30, "include_all_origins": "true"}
        ).json(),
    }


def record_change_case(
    engine: Engine, embedder: Embedder, settings: Settings, client: httpx.Client
) -> str:
    """The synthetic v3-change case, with its change analysis saved in the same transaction
    as the investigation (as an import does), before the worker can pick it up."""
    folder = CHANGE_DATASET / "cases" / CHANGE_CASE
    log_text = (folder / "failed.log").read_text(encoding="utf-8-sig")
    source = FixtureChangeSource(folder)
    failed, job = source.failed()
    lines = log_text.split("\n")
    subjects, category = failure_subjects(lines)
    analysis = analyze(failed, job, lines, source, subjects=subjects, category=category)
    with Session(engine) as session, session.begin():
        repository = ensure_repository(session, DEFAULT_WORKSPACE_ID, f"demo/{CHANGE_CASE}")
        indexed = index_directory(session, DEFAULT_WORKSPACE_ID, repository.id, folder / "repo")
        embed_pending(session, embedder, DEFAULT_WORKSPACE_ID, indexed.document_ids)
        new = NewInvestigation(None, "upload", "ollama", "job.log", log_text, repository.id)
        investigation = create_investigation(session, DEFAULT_WORKSPACE_ID, new, settings.llm_model)
        save_analysis(session, DEFAULT_WORKSPACE_ID, investigation.id, failed.head_sha, analysis)
        investigation_id = str(investigation.id)
    return str(wait_for(client, investigation_id)["id"])


@contextmanager
def serving(settings: Settings) -> Iterator[httpx.Client]:
    """Runs the real app on 127.0.0.1:PORT in this process while the block lasts."""
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=PORT, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        while not server.started:
            time.sleep(0.1)
        with httpx.Client(base_url=API, timeout=60) as client:
            yield client
    finally:
        server.should_exit = True
        thread.join(timeout=30)


def differences(a: Any, b: Any, where: str = "$") -> Iterator[str]:
    """Yields the JSON path of every value that differs between two decoded JSON documents."""
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(a.keys() | b.keys()):
            yield from differences(a.get(key), b.get(key), f"{where}.{key}")
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for index, (x, y) in enumerate(zip(a, b, strict=True)):
            yield from differences(x, y, f"{where}[{index}]")
    elif a != b:
        yield where


def verify() -> int:
    base = Settings()
    url = make_url(base.database_url.get_secret_value()).set(database=DATABASE)
    settings = base.model_copy(
        update={
            "database_url": SecretStr(url.render_as_string(hide_password=False)),
            "inference_provider": "mock",
            "embedding_provider": "mock",
            "worker_enabled": False,
        }
    )
    committed = json.loads(OUTPUT.read_text(encoding="utf-8"))
    ids = [item["id"] for item in committed["investigations"]]
    with serving(settings) as client:
        stored = export(client, ids, settings)
    found = [
        path
        # The dashboard's date range follows the day it is asked, so it is not compared.
        for key in ("investigations", "events", "documents", "samples", "history", "changes")
        for path in differences(committed[key], stored[key], f"$.{key}")
    ]
    if found:
        print(f"The recording differs from the runs stored in {DATABASE}:")
        print("\n".join(f"  {path}" for path in found[:50]))
        return 1
    print(f"{OUTPUT.relative_to(REPO_ROOT)} matches the {len(ids)} runs stored in {DATABASE}.")
    return 0


def main() -> int:
    base = Settings()
    settings = base.model_copy(
        update={
            "database_url": SecretStr(prepare_database(base, DATABASE)),
            "inference_provider": "ollama",
            "embedding_provider": "ollama",
            "worker_enabled": True,
            # Each recorded run stands alone, as in the evaluation harness.
            "index_incidents": False,
        }
    )
    engine = build_engine(settings)
    embedder = embedder_for(settings)
    if embedder is None:
        print("No embedder configured; the production settings need one.")
        return 1
    with Session(engine) as session, session.begin():
        index_knowledge(session, DEFAULT_WORKSPACE_ID, KNOWLEDGE)
        embed_pending(session, embedder, DEFAULT_WORKSPACE_ID)

    try:
        with serving(settings) as client:
            health = client.get("/api/health").json()
            if health["ollama"]["status"] != "ok":
                print(f"The local model is not ready: {health['ollama']}")
                return 1
            ids = []
            for sample in client.get("/api/samples").json():
                body = {"source": "sample", "sample_id": sample["id"], "provider": "ollama"}
                created = client.post("/api/investigations", json=body, timeout=60).json()
                ids.append(wait_for(client, created["id"])["id"])
            cases = {case.id: case for case in load_cases(DATASET, "dev")}
            for case_id in DEV_CASES:
                case = cases[case_id]
                with Session(engine) as session, session.begin():
                    repository = ensure_repository(session, DEFAULT_WORKSPACE_ID, f"demo/{case.id}")
                    indexed = index_directory(
                        session, DEFAULT_WORKSPACE_ID, repository.id, case.repo_path
                    )
                    embed_pending(session, embedder, DEFAULT_WORKSPACE_ID, indexed.document_ids)
                    # No title, as in the evaluation harness: Kensa titles it from the strongest
                    # error line. The dataset's own titles were written with the answer in mind.
                    new = NewInvestigation(
                        None,
                        "upload",
                        "ollama",
                        "job.log",
                        case.log_path.read_text(encoding="utf-8"),
                        repository.id,
                    )
                    investigation_id = str(
                        create_investigation(
                            session, DEFAULT_WORKSPACE_ID, new, settings.llm_model
                        ).id
                    )
                ids.append(wait_for(client, investigation_id)["id"])
            ids.append(record_change_case(engine, embedder, settings, client))
            recording = export(client, ids, settings)
    finally:
        engine.dispose()

    problems = check_recording(recording)
    if problems:
        print("Not written: the recording contains text that must not be published:")
        print("\n".join(f"  {p}" for p in problems))
        return 1
    OUTPUT.parent.mkdir(exist_ok=True)
    text = json.dumps(recording, ensure_ascii=False, indent=1) + "\n"
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")  # LF, as the repository stores it
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)}: {len(ids)} investigations")
    return 0


if __name__ == "__main__":
    sys.exit(verify() if sys.argv[1:] == ["--verify"] else main())
