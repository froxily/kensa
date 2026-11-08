"""M4 GitHub integration: URL parsing, redirect and SSRF guards, client behaviour, importer.

No test reaches the network: respx refuses unmocked requests, and the address checks use a
fake resolver.
"""

import ast
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpcore
import httpx
import pytest
import respx
import structlog
from pydantic import SecretStr

from kensa.github.client import ETagCache, GitHubClient, GitHubError
from kensa.github.importer import (
    MAX_FILE_BYTES,
    fit_log,
    load_run,
    referenced_paths,
    repo_path,
    select_job,
)
from kensa.github.net import PrivateAddressError, PublicAddressBackend, is_public_address
from kensa.github.urls import (
    GitHubRef,
    GitHubUrlError,
    check_log_redirect,
    parse_github_url,
    safe_url,
)
from kensa.ingestion.normalize import MAX_LINES, MAX_LOG_BYTES
from tests.conftest import BACKEND_DIR
from tests.github_fixtures import (
    API,
    JOB_ID,
    JOBS_PATH,
    LOG,
    LOGS_PATH,
    OWNER,
    REPO,
    RUN_ID,
    RUN_PATH,
    SIGNATURE,
    STORE_HOST,
    STORE_URL,
    jobs_json,
    run_json,
)

FINE_GRAINED = SecretStr("github_pat_" + "A1b2C3d4E5f6G7h8I9j0" * 3)


# ------------------------------------------------------------------------------ URL rules ---


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/pytest-dev/pytest", GitHubRef("pytest-dev", "pytest")),
        ("https://github.com/pytest-dev/pytest/actions/", GitHubRef("pytest-dev", "pytest")),
        ("https://www.github.com/a/b.c_d-e", GitHubRef("a", "b.c_d-e")),
        ("https://github.com/o/r/actions/runs/123", GitHubRef("o", "r", 123)),
        ("https://github.com/o/r/actions/runs/123/attempts/2", GitHubRef("o", "r", 123, 2)),
        (
            "https://github.com/o/r/actions/runs/123/job/456?pr=7#step:4:1",
            GitHubRef("o", "r", 123, job_id=456),
        ),
    ],
)
def test_supported_github_urls(url: str, expected: GitHubRef) -> None:
    assert parse_github_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/o/r",
        "https://github.com.evil.example/o/r",
        "https://gist.github.com/o/r",
        "https://user:pass@github.com/o/r",
        "https://github.com:8443/o/r",
        "https://github.com/o",
        "https://github.com/o/../r",
        "https://github.com/-bad/r",
        "https://github.com/o/r.git",
        "https://github.com/o/r/actions/runs/0",
        "https://github.com/o/r/actions/runs/12x",
        "https://github.com/o/r/actions/runs/1/logs",
        "https://github.com/o/r/pulls",
        "javascript:alert(1)",
        "https://github.com/o/r /actions",
        "https://github.com/" + "o/" * 300,
    ],
)
def test_unsupported_or_unsafe_urls_are_refused(url: str) -> None:
    with pytest.raises(GitHubUrlError):
        parse_github_url(url)


def test_allowlisted_log_redirect_is_accepted_and_query_never_shown() -> None:
    assert check_log_redirect(STORE_URL).hostname == STORE_HOST
    shown = safe_url(STORE_URL)
    assert SIGNATURE not in shown
    assert "?" not in shown


@pytest.mark.parametrize(
    "location",
    [
        None,
        "",
        STORE_URL.replace("https://", "http://"),
        STORE_URL.replace(STORE_HOST, f"{STORE_HOST}:8443"),
        STORE_URL.replace(STORE_HOST, f"user@{STORE_HOST}"),
        "https://10.0.0.5/logs.txt",
        "https://[::1]/logs.txt",
        "https://169.254.169.254/latest/meta-data/",
        STORE_URL.replace(STORE_HOST, f"{STORE_HOST}.evil.example"),
        STORE_URL.replace(STORE_HOST, "attacker.blob.core.windows.net"),
        "https://example.com/logs.txt",
        "file:///etc/passwd",
    ],
)
def test_unsafe_log_redirects_are_refused(location: str | None) -> None:
    with pytest.raises(GitHubUrlError):
        check_log_redirect(location)


# --------------------------------------------------------------------------- address guard ---


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("140.82.112.6", True),
        ("2606:50c0:8000::154", True),
        ("10.1.2.3", False),
        ("172.16.0.1", False),
        ("192.168.1.10", False),
        ("127.0.0.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),  # noqa: S104
        ("::1", False),
        ("fe80::1", False),
        ("::ffff:127.0.0.1", False),
        ("224.0.0.1", False),
        ("not-an-ip", False),
    ],
)
def test_only_globally_routable_addresses_are_public(address: str, public: bool) -> None:
    assert is_public_address(address) is public


class RecordingBackend(httpcore.NetworkBackend):
    def __init__(self) -> None:
        self.connected: list[str] = []

    def connect_tcp(self, host: str, port: int, *args: Any, **kwargs: Any) -> Any:
        self.connected.append(host)
        raise httpcore.ConnectError("recorded, not connected")


def test_backend_refuses_private_resolution_before_connecting() -> None:
    inner = RecordingBackend()
    backend = PublicAddressBackend(lambda host, port: ["93.184.215.14", "10.0.0.7"], inner)
    with pytest.raises(PrivateAddressError):
        backend.connect_tcp(STORE_HOST, 443)
    assert inner.connected == []


def test_backend_connects_to_the_vetted_address_only() -> None:
    inner = RecordingBackend()
    backend = PublicAddressBackend(lambda host, port: ["140.82.112.6"], inner)
    with pytest.raises(httpcore.ConnectError):
        backend.connect_tcp("api.github.com", 443)
    assert inner.connected == ["140.82.112.6"]
    with pytest.raises(httpcore.ConnectError):
        backend.connect_unix_socket("/var/run/docker.sock")


# --------------------------------------------------------------------------------- client ---


@pytest.fixture
def client() -> Iterator[GitHubClient]:
    with GitHubClient(cache=ETagCache()) as github:
        yield github


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as mock:
        yield mock


def _json(status: int, body: Any, **headers: str) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers)


def test_conditional_requests_reuse_the_cached_body(
    client: GitHubClient, router: respx.MockRouter
) -> None:
    route = router.get(f"{API}{RUN_PATH}").mock(
        side_effect=[_json(200, run_json(), etag='W/"v1"'), httpx.Response(304)]
    )
    first = client.get_json(RUN_PATH, what="run")
    second = client.get_json(RUN_PATH, what="run")
    assert first == second
    assert route.calls[1].request.headers["if-none-match"] == 'W/"v1"'


@pytest.mark.parametrize(
    ("response", "code", "status"),
    [
        (_json(404, {"message": "Not Found"}), "not_found", 404),
        (_json(410, {"message": "Gone"}), "gone", 410),
        (_json(401, {"message": "Bad credentials"}), "token_rejected", 502),
        (_json(403, {"message": "Resource not accessible"}), "forbidden", 403),
        (
            _json(
                403,
                {"message": "API rate limit exceeded"},
                **{"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1793348428"},
            ),
            "rate_limited",
            429,
        ),
        (_json(429, {"message": "slow down"}, **{"retry-after": "30"}), "rate_limited", 429),
        (_json(500, {"message": "boom"}), "upstream_error", 502),
    ],
)
def test_github_errors_are_typed(
    client: GitHubClient, router: respx.MockRouter, response: httpx.Response, code: str, status: int
) -> None:
    router.get(f"{API}{RUN_PATH}").mock(return_value=response)
    with pytest.raises(GitHubError) as caught:
        client.get_json(RUN_PATH, what="run")
    assert (caught.value.code, caught.value.status) == (code, status)
    if code == "rate_limited":
        assert caught.value.retry_at is not None
        assert "Try again after" in caught.value.message


def test_timeouts_and_oversized_responses_are_typed(
    client: GitHubClient, router: respx.MockRouter
) -> None:
    router.get(f"{API}{RUN_PATH}").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(GitHubError) as caught:
        client.get_json(RUN_PATH, what="run")
    assert caught.value.code == "timeout"
    router.get(f"{API}{JOBS_PATH}").mock(return_value=httpx.Response(200, content=b"x" * 3_000_001))
    with pytest.raises(GitHubError) as caught:
        client.get_json(JOBS_PATH, what="jobs")
    assert caught.value.code == "response_too_large"


def test_only_repository_reads_are_possible(client: GitHubClient) -> None:
    for path in ("/user", "/orgs/x", "/repos/o/r/../../user"):
        with pytest.raises(GitHubError):
            client.get_json(path, what="x")
    public = {n for n in dir(GitHubClient) if not n.startswith("_")}
    assert public == {"authenticated", "close", "get_json", "job_log", "file_at"}


def test_the_github_cli_login_token_is_refused() -> None:
    with pytest.raises(GitHubError) as caught:
        GitHubClient(token=SecretStr("gho_" + "x" * 36))
    assert caught.value.code == "token_refused"


def test_a_token_with_oauth_scopes_is_refused(router: respx.MockRouter) -> None:
    router.get(f"{API}{RUN_PATH}").mock(
        return_value=_json(200, run_json(), **{"x-oauth-scopes": "repo, workflow"})
    )
    with (
        GitHubClient(token=SecretStr("ghp_" + "y" * 36), cache=ETagCache()) as github,
        pytest.raises(GitHubError) as caught,
    ):
        github.get_json(RUN_PATH, what="run")
    assert caught.value.code == "token_refused"


def test_anonymous_log_download_explains_the_token_requirement(
    client: GitHubClient, router: respx.MockRouter
) -> None:
    router.get(f"{API}{LOGS_PATH}").mock(
        return_value=_json(403, {"message": "Must have admin rights to Repository."})
    )
    with pytest.raises(GitHubError) as caught:
        client.job_log(OWNER, REPO, JOB_ID)
    assert caught.value.code == "logs_need_token"


@pytest.mark.parametrize("status", [404, 410])
def test_expired_logs_are_reported(
    client: GitHubClient, router: respx.MockRouter, status: int
) -> None:
    router.get(f"{API}{LOGS_PATH}").mock(return_value=_json(status, {"message": "x"}))
    with pytest.raises(GitHubError) as caught:
        client.job_log(OWNER, REPO, JOB_ID)
    assert caught.value.code == "logs_unavailable"


def test_log_redirect_is_followed_once_without_credentials(router: respx.MockRouter) -> None:
    api = router.get(f"{API}{LOGS_PATH}").mock(
        return_value=httpx.Response(
            302, headers={"location": STORE_URL, "set-cookie": "session=abc; Path=/"}
        )
    )
    store = router.get(host=STORE_HOST).mock(
        return_value=httpx.Response(
            200, content=LOG.encode(), headers={"content-type": "text/plain"}
        )
    )
    with (
        structlog.testing.capture_logs() as logs,
        GitHubClient(token=FINE_GRAINED, cache=ETagCache()) as github,
    ):
        download = github.job_log(OWNER, REPO, JOB_ID)
    assert download.content == LOG.encode()
    assert (download.via_redirect, download.host) == (True, STORE_HOST)
    assert api.calls[0].request.headers["authorization"].startswith("Bearer github_pat_")
    sent = store.calls[0].request.headers
    assert "authorization" not in sent
    assert "cookie" not in sent
    assert SIGNATURE not in json.dumps(logs, default=str)


@pytest.mark.parametrize(
    ("location", "store_called"),
    [
        ("https://evil.example/steal", False),
        (STORE_URL.replace("https://", "http://"), False),
        ("https://127.0.0.1/logs", False),
        (None, False),
    ],
)
def test_disallowed_log_redirects_are_never_requested(
    client: GitHubClient, router: respx.MockRouter, location: str | None, store_called: bool
) -> None:
    headers = {"location": location} if location else {}
    router.get(f"{API}{LOGS_PATH}").mock(return_value=httpx.Response(302, headers=headers))
    other = router.route().mock(return_value=httpx.Response(200, content=b"leak"))
    with structlog.testing.capture_logs() as logs, pytest.raises(GitHubError) as caught:
        client.job_log(OWNER, REPO, JOB_ID)
    assert caught.value.code == "redirect_refused"
    assert other.called is store_called
    assert SIGNATURE not in caught.value.message
    assert SIGNATURE not in json.dumps(logs, default=str)


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(302, headers={"location": STORE_URL}), "redirect_refused"),
        (httpx.Response(403, content=b"AuthenticationFailed"), "logs_unavailable"),
        (httpx.Response(200, content=b"PK\x03\x04zipdata"), "unsupported_content"),
        (
            httpx.Response(200, content=b"x", headers={"content-type": "application/zip"}),
            "unsupported_content",
        ),
        (httpx.Response(200, content=b"x" * 200_001), "response_too_large"),
    ],
)
def test_the_log_store_answer_is_checked(
    router: respx.MockRouter, response: httpx.Response, code: str
) -> None:
    router.get(f"{API}{LOGS_PATH}").mock(
        return_value=httpx.Response(302, headers={"location": STORE_URL})
    )
    router.get(host=STORE_HOST).mock(return_value=response)
    with (
        GitHubClient(cache=ETagCache(), max_log_bytes=200_000) as github,
        pytest.raises(GitHubError) as caught,
    ):
        github.job_log(OWNER, REPO, JOB_ID)
    assert caught.value.code == code
    assert SIGNATURE not in caught.value.message


def test_a_log_store_resolving_to_a_private_address_is_never_contacted(
    router: respx.MockRouter,
) -> None:
    router.get(f"{API}{LOGS_PATH}").mock(
        return_value=httpx.Response(302, headers={"location": STORE_URL})
    )
    router.get(host=STORE_HOST).pass_through()  # reach the real transport and its address check
    inner = RecordingBackend()
    private = PublicAddressBackend(lambda host, port: ["127.0.0.1"], inner)
    with (
        GitHubClient(cache=ETagCache(), network=private) as github,
        pytest.raises(GitHubError) as caught,
    ):
        github.job_log(OWNER, REPO, JOB_ID)
    assert caught.value.code == "redirect_refused"
    assert inner.connected == []


# ------------------------------------------------------------------------------- importer ---


def test_paths_in_the_log_are_mapped_into_the_repository() -> None:
    assert (
        repo_path("/home/runner/work/demo-app/demo-app/src/demo/config.py") == "src/demo/config.py"
    )
    assert repo_path(r"D:\a\demo-app\demo-app\tests\test_x.py") == "tests/test_x.py"
    assert repo_path("/github/workspace/app/main.go") == "app/main.go"
    assert repo_path("./tests/conftest.py") == "tests/conftest.py"
    for outside in (
        "/opt/hostedtoolcache/Python/3.12.7/x64/lib/python3.12/site-packages/x.py",
        "/usr/lib/python3/os.py",
        "../secrets.py",
        "node_modules/pkg/index.js",
        "C:/Windows/system.ini",
        "https://docs.example.invalid/setup.py",
    ):
        assert repo_path(outside) is None


def test_referenced_paths_favour_the_failure() -> None:
    paths = referenced_paths(LOG, limit=6)
    assert paths[:2] == ["tests/conftest.py", "src/demo/config.py"]
    assert not any("site-packages" in p or "docs.example" in p for p in paths)
    assert referenced_paths(LOG, limit=1) == ["tests/conftest.py"]


def test_an_over_long_log_keeps_its_end_and_says_so() -> None:
    small, dropped = fit_log(LOG)
    assert dropped == 0
    assert small.rstrip("\n") == LOG.replace("\r\n", "\n").rstrip("\n")
    huge = "\n".join(f"line {i} " + "x" * 80 for i in range(60_000)) + "\nFINAL ERROR"
    kept, dropped = fit_log(huge)
    lines = kept.split("\n")
    assert dropped > 0
    assert lines[0].startswith("[Kensa: the first")
    assert "truncated" in lines[0]
    assert lines[-1] == "FINAL ERROR"
    assert len(kept.encode()) <= MAX_LOG_BYTES
    assert len(lines) <= MAX_LINES


def test_run_states_that_cannot_be_investigated(
    client: GitHubClient, router: respx.MockRouter
) -> None:
    ref = GitHubRef(OWNER, REPO, RUN_ID)
    route = router.get(f"{API}{RUN_PATH}")
    for payload, code in (
        (run_json(repository={"private": True}), "private_repository"),
        (run_json(status="in_progress", conclusion=None), "run_in_progress"),
        (run_json(conclusion="success"), "run_not_failed"),
    ):
        route.mock(return_value=_json(200, payload))
        with GitHubClient(cache=ETagCache()) as fresh, pytest.raises(GitHubError) as caught:
            load_run(fresh, ref)
        assert caught.value.code == code
    route.mock(return_value=_json(200, run_json()))
    router.get(f"{API}{JOBS_PATH}").mock(return_value=_json(200, jobs_json()))
    _, run, jobs = load_run(client, ref)
    assert run.head_sha.startswith("0123456")
    assert [j.id for j in jobs] == [JOB_ID]  # the successful job is not offered
    assert [s.name for s in jobs[0].failed_steps] == ["Run tests"]
    assert select_job(jobs, None).id == JOB_ID
    with pytest.raises(GitHubError):
        select_job(jobs, 1)
    with pytest.raises(GitHubError):
        select_job([], None)
    assert MAX_FILE_BYTES == 200_000


# ------------------------------------------------------------------- no writes, no execution ---

GITHUB_PACKAGE = BACKEND_DIR / "src" / "kensa" / "github"


def _calls(path: Path) -> tuple[set[str], list[ast.Call]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    streams: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                names.add(func.attr)
                if func.attr == "stream":
                    streams.append(node)
            elif isinstance(func, ast.Name):
                names.add(func.id)
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.upper() in {"POST", "PUT", "PATCH", "DELETE"}
        ):
            names.add(f"method:{node.value.upper()}")
    return names, streams


def test_the_github_package_only_reads_and_never_executes() -> None:
    forbidden = {
        "post",
        "put",
        "patch",
        "delete",
        "request",
        "send",
        "method:POST",
        "method:PUT",
        "method:PATCH",
        "method:DELETE",
        "eval",
        "exec",
        "system",
        "popen",
        "Popen",
        "check_output",
        "extractall",
    }
    stream_count = 0
    for path in GITHUB_PACKAGE.glob("*.py"):
        names, streams = _calls(path)
        assert not (names & forbidden), (path.name, names & forbidden)
        for call in streams:  # every HTTP request is a literal GET
            first = call.args[0] if call.args else None
            assert isinstance(first, ast.Constant), path.name
            assert first.value == "GET", path.name
        stream_count += len(streams)
        source = path.read_text(encoding="utf-8")
        assert "import subprocess" not in source
        assert "import pickle" not in source
    assert stream_count == 2
