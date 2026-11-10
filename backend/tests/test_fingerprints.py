"""v1.1 failure fingerprints and similar failures (D-051, D-053)."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from kensa.agents.handler import make_investigate_handler, on_job_outcome
from kensa.analysis.causes import assess_causes
from kensa.analysis.classifier import classify
from kensa.analysis.fingerprint import Fingerprint, fingerprints, mask
from kensa.analysis.signatures import extract_signatures
from kensa.app import create_app
from kensa.core.config import Settings
from kensa.db.models import (
    DEFAULT_WORKSPACE_ID,
    Diagnosis,
    Document,
    FailureFingerprint,
    Investigation,
    InvestigationFingerprint,
    Workspace,
)
from kensa.history.fingerprints import confirm_resolution, similar_failures
from kensa.history.quality import run_checks
from kensa.investigations.service import (
    INVESTIGATE_JOB,
    RESUME_JOB,
    NewInvestigation,
    create_investigation,
)
from kensa.jobs.worker import Worker

WS = DEFAULT_WORKSPACE_ID


def _log(variable: str, *, day: int = 3, run: int = 41, line: int = 12, tmp: str = "abc") -> str:
    return "\n".join(
        [
            f"2026-11-0{day}T08:00:01.1234567Z ##[group]Run pytest",
            f"2026-11-0{day}T08:00:02.1234567Z platform linux -- Python 3.12.7, pytest-8.4.2",
            f"2026-11-0{day}T08:00:03.1234567Z rootdir: /home/runner/work/app{run}/app{run}",
            f"2026-11-0{day}T08:00:04.1234567Z cache: /tmp/pytest-of-runner/pytest-{tmp}/c0",
            f"2026-11-0{day}T08:00:05.1234567Z src/settings.py:{line}: in <module>",
            f'2026-11-0{day}T08:00:05.2234567Z     REGION = os.environ["{variable}"]',
            f"2026-11-0{day}T08:00:05.3234567Z E   KeyError: '{variable}'",
            f"2026-11-0{day}T08:00:06.1234567Z ERROR tests/test_app.py - KeyError: '{variable}'",
            f"2026-11-0{day}T08:00:07.1234567Z ##[error]Process completed with exit code "
            f"{run % 3 + 1}.",
        ]
    )


def _test_log(assertion: str, *, line: int = 30, duration: str = "1.42s") -> str:
    return "\n".join(
        [
            "2026-11-03T08:00:01.0000000Z ##[group]Run pytest",
            f"2026-11-03T08:00:02.0000000Z tests/test_price.py:{line}: AssertionError",
            f"2026-11-03T08:00:02.1000000Z E   {assertion}",
            "2026-11-03T08:00:03.0000000Z =========================== short test summary info",
            f"2026-11-03T08:00:03.1000000Z FAILED tests/test_price.py::test_rounding - {assertion}",
            f"2026-11-03T08:00:04.0000000Z ======== 1 failed, 12 passed in {duration} ========",
            "2026-11-03T08:00:05.0000000Z ##[error]Process completed with exit code 1.",
        ]
    )


def _prints(log: str) -> list[str]:
    lines = log.split("\n")
    signatures = extract_signatures(lines)
    causes = assess_causes(lines)
    rule = classify(signatures, causes)
    return [f.hash for f in fingerprints(lines, signatures, causes, rule.category)]


# ------------------------------------------------------------------ the algorithm ---


def test_mask_removes_what_varies_between_recurrences_but_keeps_versions() -> None:
    line = (
        "2026-11-03T08:00:01.123Z /home/runner/work/app/app/src/x.py:42 took 3.5s on "
        "10.1.2.3:5432 sha 9f86d081884c7d659a2feaa0c55ad015 id "
        "123e4567-e89b-12d3-a456-426614174000 python 3.12 run #812 /tmp/pytest-of-r/pytest-7/a.txt"
    )
    masked = mask(line)
    assert "src/x.py:<line>" in masked
    assert "<dur>" in masked
    assert "<ip>" in masked
    assert "<hex>" in masked
    assert "<uuid>" in masked
    assert "python 3.12" in masked  # versions are part of what failed
    assert "#<n>" in masked
    assert "<tmp>/a.txt" in masked
    assert "/home/runner" not in masked
    assert "2026" not in masked


def test_a_recurrence_with_different_noise_gets_the_same_fingerprint() -> None:
    first = _prints(_log("ORCHARD_REGION"))
    again = _prints(_log("ORCHARD_REGION", day=5, run=97, line=14, tmp="xyz"))
    assert first
    assert first[0] == again[0]


def test_a_lookalike_with_another_variable_gets_another_fingerprint() -> None:
    assert _prints(_log("ORCHARD_REGION"))[0] != _prints(_log("ORCHARD_ZONE"))[0]


def test_one_test_failing_for_different_reasons_is_not_one_failure() -> None:
    rounding = _prints(_test_log("assert 10.0 == 10.01"))
    rounding_again = _prints(_test_log("assert 10.0 == 10.01", line=33, duration="2.07s"))
    other = _prints(_test_log("KeyError: 'currency'"))
    assert rounding[0] == rounding_again[0]
    assert rounding[0] != other[0]


def _step_log(command: str, failure: list[str]) -> str:
    return "\n".join(
        [
            f"2026-11-03T08:00:01.0000000Z ##[group]Run {command}",
            f"2026-11-03T08:00:01.1000000Z {command}",
            "2026-11-03T08:00:01.2000000Z ##[endgroup]",
            *[f"2026-11-03T08:00:0{i + 2}.0000000Z {line}" for i, line in enumerate(failure)],
            "2026-11-03T08:00:09.0000000Z ##[error]Process completed with exit code 1.",
        ]
    )


def test_a_source_position_never_tells_one_test_failure_from_its_recurrence() -> None:
    def go_log(line: int) -> str:
        return _step_log(
            "go test ./...",
            [
                f"    refund_test.go:{line}: refund 10.005: got 10.00, want 10.01",
                "--- FAIL: TestRefundRounding (0.00s)",
                "FAIL\texample.com/refunds\t0.012s",
            ],
        )

    assert _prints(go_log(41))[0] == _prints(go_log(58))[0]
    assert (
        mask("src/a.cs(12,5): error CS0266", keep_numbers=True) == "src/a.cs(<line>): error cs0266"
    )


def test_a_line_that_names_its_failure_matches_whatever_command_ran_it() -> None:
    failure = ["src/render.ts(14,9): error TS2345: Argument of type 'number' is not assignable."]
    typecheck = _prints(_step_log("npm run typecheck", failure))
    build = _prints(_step_log("npm run build --if-present", failure))
    assert typecheck[0] == build[0]


def _primary(log: str) -> Fingerprint:
    lines = log.split("\n")
    signatures = extract_signatures(lines)
    causes = assess_causes(lines)
    rule = classify(signatures, causes)
    return fingerprints(lines, signatures, causes, rule.category)[0]


def test_a_failure_that_names_nothing_specific_is_approximate_never_a_recurrence() -> None:
    """D-057: two different jobs cancelled with the same generic line must not be claimed as one
    failure, so such a fingerprint is approximate (similar, not the same)."""
    cancelled = ["Error: The operation was canceled."]
    assert _primary(_step_log("npm run e2e", cancelled)).kind == "approximate"
    assert _primary(_step_log("cargo test --workspace", cancelled)).kind == "approximate"


def test_a_failure_with_a_named_subject_is_exact() -> None:
    assert _primary(_log("ORCHARD_REGION")).kind == "exact"


def test_one_failure_reported_by_different_rules_is_still_one_failure() -> None:
    """A missing module is the same failure whether the run reports ModuleNotFoundError or
    an import error naming it (rule families, D-057)."""
    by_error = _step_log("pytest", ["E   ModuleNotFoundError: No module named 'quillon.ledger'"])
    by_import = _step_log(
        "python -m pytest -q", ["ModuleNotFoundError: No module named 'quillon.ledger'"]
    )
    other = _step_log("pytest", ["E   ModuleNotFoundError: No module named 'quillon.audit'"])
    assert _primary(by_error).hash == _primary(by_import).hash
    assert _primary(by_error).hash != _primary(other).hash


def test_a_summary_points_back_to_the_error_it_summarises() -> None:
    def mypy(name: str) -> str:
        return _step_log(
            "mypy src",
            [
                f'src/app/ledger.py:12: error: Name "{name}" is not defined  [name-defined]',
                "Found 1 error in 1 file (checked 14 source files)",
            ],
        )

    assert _primary(mypy("totals")).kind == "exact"
    assert _primary(mypy("totals")).hash != _primary(mypy("balance")).hash


def test_an_image_pull_failure_is_named_by_the_image_its_step_pulled() -> None:
    def pull(image: str) -> str:
        return _step_log(f"docker pull {image}", ["Error response from daemon: manifest unknown"])

    relay = _prints(pull("ghcr.io/acme/relay-base:4.8"))
    assert relay[0] == _prints(pull("ghcr.io/acme/relay-base:4.8"))[0]
    assert relay[0] != _prints(pull("ghcr.io/acme/probe-base:2.7"))[0]


def test_composer_resolution_failures_are_named_by_the_root_requirement() -> None:
    def composer(package: str, found: str) -> str:
        return _step_log(
            "composer update --no-interaction",
            [
                "Your requirements could not be resolved to an installable set of packages.",
                "  Problem 1",
                f"    - Root composer.json requires {package} ^4.0, found {package}[{found}] "
                "but it does not match the constraint.",
            ],
        )

    calendar = composer("acme/calendar-core", "3.0.0, 3.2.0")
    signatures = extract_signatures(calendar.split("\n"))
    unresolvable = [s for s in signatures if s.rule_id == "composer.unresolvable"]
    assert [s.value for s in unresolvable] == ["acme/calendar-core"]
    assert unresolvable[0].category == "dependency_build"
    again = composer("acme/calendar-core", "3.0.0, 3.2.0, 3.3.0")
    assert _prints(calendar)[0] == _prints(again)[0]
    assert _prints(calendar)[0] != _prints(composer("acme/tax-rules", "6.1.0"))[0]


def test_a_log_without_any_signal_has_no_fingerprint() -> None:
    assert _prints("2026-11-03T08:00:01.0000000Z all good\n2026-11-03T08:00:02Z done") == []


# --------------------------------------------------------------- similar failures ---


def _create(engine: Engine, log: str, title: str = "t") -> uuid.UUID:
    with Session(engine) as session, session.begin():
        new = NewInvestigation(
            title=title, source="paste", provider="mock", document_name="job.log", log_text=log
        )
        return create_investigation(session, WS, new, None).id


def _diagnose(engine: Engine, investigation_id: uuid.UUID, category: str, status: str) -> None:
    with Session(engine) as session, session.begin():
        session.add(
            Diagnosis(
                workspace_id=WS,
                investigation_id=investigation_id,
                category=category,
                summary="s",
                root_cause="r",
                confidence=0.5,
                uncertainty="",
                recommended_fixes=[],
                verification_status=status,
                verification_notes=[],
                provider="mock",
            )
        )


@pytest.mark.db
def test_a_recurrence_is_found_as_the_same_failure_and_a_lookalike_is_not(
    db_engine: Engine,
) -> None:
    first = _create(db_engine, _log("ORCHARD_REGION"))
    lookalike = _create(db_engine, _log("ORCHARD_ZONE", day=4))
    again = _create(db_engine, _log("ORCHARD_REGION", day=5, run=97, line=14))
    _diagnose(db_engine, first, "missing_env_var", "corroborated")
    with Session(db_engine) as session:
        found = similar_failures(session, WS, again, earlier_only=True)
    assert found[0].investigation_id == first
    assert found[0].match == "same_failure"
    assert found[0].score == 1.0
    assert found[0].provenance == "verifier_corroborated"
    assert all(s.match != "same_failure" for s in found if s.investigation_id == lookalike)


@pytest.mark.db
def test_a_shared_approximate_fingerprint_is_only_similar(db_engine: Engine) -> None:
    """The same generic line in two logs is shown as a similar failure, never as the same."""
    log = _step_log("npm run e2e", ["Error: The operation was canceled."])
    first = _create(db_engine, log)
    again = _create(db_engine, log.replace("08:00", "09:00"))
    with Session(db_engine) as session:
        found = similar_failures(session, WS, again, earlier_only=True)
    assert [s.investigation_id for s in found] == [first]
    assert found[0].match == "similar_text"
    assert found[0].score < 1.0


@pytest.mark.db
def test_one_failure_is_never_its_own_recurrence(db_engine: Engine) -> None:
    log = _log("ORCHARD_REGION")
    first = _create(db_engine, log)
    identical = _create(db_engine, log)  # the same log investigated twice
    with Session(db_engine) as session:
        assert similar_failures(session, WS, identical) == []
        assert similar_failures(session, WS, first) == []


@pytest.mark.db
def test_a_confirmed_resolution_is_shown_but_changes_no_diagnosis(db_engine: Engine) -> None:
    first = _create(db_engine, _log("ORCHARD_REGION"))
    again = _create(db_engine, _log("ORCHARD_REGION", day=6, run=12))
    _diagnose(db_engine, first, "missing_env_var", "plausible")
    with Session(db_engine) as session, session.begin():
        confirm_resolution(session, WS, first, "Added ORCHARD_REGION to the deploy job's env.")
        confirm_resolution(session, WS, first, "Added ORCHARD_REGION to the job env.")
    with Session(db_engine) as session:
        found = similar_failures(session, WS, again)
        status = session.execute(
            select(Diagnosis.verification_status).where(Diagnosis.investigation_id == first)
        ).scalar_one()
    assert found[0].provenance == "human_confirmed"
    assert found[0].resolution == "Added ORCHARD_REGION to the job env."  # the latest only
    assert status == "plausible"


@pytest.mark.db
def test_a_wrong_earlier_diagnosis_cannot_change_a_later_one(
    db_engine: Engine, test_database_url: str
) -> None:
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        inference_provider="mock",
        embedding_provider="mock",
        worker_enabled=False,
    )
    handler = make_investigate_handler(settings)
    worker = Worker(
        db_engine, {INVESTIGATE_JOB: handler, RESUME_JOB: handler}, on_outcome=on_job_outcome
    )

    def result(investigation_id: uuid.UUID) -> tuple[str, str]:
        with Session(db_engine) as session:
            row = session.execute(
                select(Diagnosis.category, Diagnosis.verification_status).where(
                    Diagnosis.investigation_id == investigation_id
                )
            ).one()
        return row.category, row.verification_status

    control = _create(db_engine, _log("ORCHARD_REGION"))
    while worker.run_once():
        pass
    expected = result(control)
    # The earlier investigation's conclusion is now wrong, and claims to be corroborated.
    with Session(db_engine) as session, session.begin():
        session.execute(
            text(
                "UPDATE diagnoses SET category = 'docker', verification_status = 'corroborated', "
                "root_cause = 'The base image is missing.' WHERE investigation_id = :i"
            ),
            {"i": control},
        )
    later = _create(db_engine, _log("ORCHARD_REGION", day=7, run=55))
    while worker.run_once():
        pass
    assert result(later) == expected
    with Session(db_engine) as session:
        incidents = session.execute(
            select(func.count()).select_from(Document).where(Document.source_type == "incident")
        ).scalar_one()
        found = similar_failures(session, WS, later)
    assert incidents == 0  # model conclusions no longer join the evidence pool
    assert found[0].investigation_id == control  # shown as history, labelled by provenance
    assert found[0].diagnosis_category == "docker"


@pytest.mark.db
def test_one_fingerprint_with_different_diagnoses_is_a_quality_finding(db_engine: Engine) -> None:
    first = _create(db_engine, _log("ORCHARD_REGION"))
    again = _create(db_engine, _log("ORCHARD_REGION", day=5, run=9))
    _diagnose(db_engine, first, "missing_env_var", "corroborated")
    _diagnose(db_engine, again, "db_connectivity", "plausible")
    with Session(db_engine) as session, session.begin():
        found = run_checks(session, WS)
    assert found["fingerprint_category_conflict"] == 1


@pytest.mark.db
def test_purging_the_last_investigation_removes_its_fingerprints(db_engine: Engine) -> None:
    from kensa.history.purge import purge_investigations

    only = _create(db_engine, _log("ORCHARD_REGION"))
    with Session(db_engine) as session, session.begin():
        counts = purge_investigations(session, WS, [only])
    assert counts["fingerprints"] >= 1
    with Session(db_engine) as session:
        assert (
            session.execute(select(func.count()).select_from(FailureFingerprint)).scalar_one() == 0
        )
        assert (
            session.execute(select(func.count()).select_from(InvestigationFingerprint)).scalar_one()
            == 0
        )


# ----------------------------------------------------------------------------- API ---


@pytest.fixture
def client(db_engine: Engine, test_database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        worker_enabled=False,
        inference_provider="mock",
        embedding_provider="mock",
        history_matching=True,  # experimental, off by default (D-057)
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def default_client(db_engine: Engine, test_database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        worker_enabled=False,
        inference_provider="mock",
        embedding_provider="mock",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.mark.db
def test_history_and_resolution_through_the_api(client: TestClient, db_engine: Engine) -> None:
    first = _create(db_engine, _log("ORCHARD_REGION"), title="first")
    again = _create(db_engine, _log("ORCHARD_REGION", day=5, run=97))
    body = client.get(f"/api/investigations/{again}/history").json()
    assert body["fingerprints"][0]["role"] == "primary"
    assert body["fingerprints"][0]["occurrences"] == 2
    assert body["similar"][0]["investigation_id"] == str(first)
    assert body["similar"][0]["provenance"] == "none"
    assert body["resolution"] is None

    short = client.post(f"/api/investigations/{first}/resolution", json={"summary": "x"})
    assert short.status_code == 422
    done = client.post(
        f"/api/investigations/{first}/resolution", json={"summary": "Set the variable."}
    )
    assert done.status_code == 201
    assert done.json()["provenance"] == "human_confirmed"
    events = client.get(f"/api/investigations/{first}/events").json()
    assert events[-1]["node"] == "resolution"
    assert (
        client.get(f"/api/investigations/{again}/history").json()["similar"][0]["resolution"]
        == "Set the variable."
    )


@pytest.mark.db
def test_another_workspaces_history_is_not_found(client: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session, session.begin():
        other = Workspace(name=f"other-{uuid.uuid4().hex[:6]}")
        session.add(other)
        session.flush()
        foreign = Investigation(workspace_id=other.id, title="x", source="paste", provider="mock")
        session.add(foreign)
        session.flush()
        foreign_id, other_id = foreign.id, other.id
    assert client.get(f"/api/investigations/{foreign_id}/history").status_code == 404
    response = client.post(
        f"/api/investigations/{foreign_id}/resolution", json={"summary": "Something."}
    )
    assert response.status_code == 404
    with Session(db_engine) as session, session.begin():
        session.execute(text("DELETE FROM workspaces WHERE id = :i"), {"i": other_id})


@pytest.mark.db
def test_history_matching_is_off_by_default(default_client: TestClient, db_engine: Engine) -> None:
    """It missed two held-out thresholds (v1.1.0 protocol): by default nothing is matched,
    counted or claimed as a recurrence, while the fingerprints are still recorded."""
    _create(db_engine, _log("ORCHARD_REGION"), title="first")
    again = _create(db_engine, _log("ORCHARD_REGION", day=5, run=97))
    body = default_client.get(f"/api/investigations/{again}/history").json()
    assert body["matching"] is False
    assert body["similar"] == []
    assert body["fingerprints"][0]["role"] == "primary"
    assert body["fingerprints"][0]["occurrences"] is None
