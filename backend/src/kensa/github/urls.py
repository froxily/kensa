"""Strict parsing of user-supplied GitHub URLs and of GitHub's log-download redirects.

Only ``https://github.com/<owner>/<repo>`` pages of a repository, its Actions tab, a run, a run
attempt or a job are accepted. Every component is checked against GitHub's own naming rules, so
API paths are built from validated parts only, never from user text.

Log downloads: ``GET /repos/{o}/{r}/actions/jobs/{id}/logs`` answers with a redirect to a
short-lived signed URL on GitHub's log storage. ``check_log_redirect`` accepts exactly one hop to
an allowlisted HTTPS host on port 443, without userinfo and never to an IP literal. Address
checks at connect time (``kensa.github.net``) cover DNS answers that point inside the network.
Signed URLs carry credentials in their query string, so ``safe_url`` drops it before a URL is
logged, stored or shown.
"""

import re
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import SplitResult, urlsplit

GITHUB_HOSTS = frozenset({"github.com", "www.github.com"})
OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
REPO = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
NUMBER = re.compile(r"^[1-9][0-9]{0,19}$")

# GitHub's job-log stores (DECISIONS.md D-032). Confirmed 2026-10-30 by a real authenticated
# download, which redirected to productionresultssa6.blob.core.windows.net. Exact names or
# tight patterns only: a broad suffix such as *.blob.core.windows.net would admit storage
# anyone can create. An unknown host fails closed (redirect_refused).
LOG_HOST_PATTERNS = (
    re.compile(r"^productionresultssa[0-9]{1,2}\.blob\.core\.windows\.net$"),
    re.compile(r"^pipelines\.actions\.githubusercontent\.com$"),
    re.compile(r"^results-receiver\.actions\.githubusercontent\.com$"),
)


class GitHubUrlError(ValueError):
    """The URL is not a supported GitHub repository, run or job address."""


@dataclass(frozen=True)
class GitHubRef:
    owner: str
    repo: str
    run_id: int | None = None
    attempt: int | None = None
    job_id: int | None = None

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


def _number(value: str, what: str) -> int:
    if not NUMBER.match(value):
        raise GitHubUrlError(f"{what} must be a positive number")
    return int(value)


def check_name(owner: str, repo: str) -> None:
    if not OWNER.match(owner):
        raise GitHubUrlError("invalid repository owner")
    if not REPO.match(repo) or repo in {".", ".."} or repo.endswith(".git"):
        raise GitHubUrlError("invalid repository name")


def parse_github_url(text: str) -> GitHubRef:
    """Parse a repository, Actions, run, run-attempt or job URL. Query and fragment (such as
    ``?pr=12``) are ignored; anything else unexpected is refused."""
    raw = text.strip()
    if len(raw) > 500 or any(ch.isspace() for ch in raw):
        raise GitHubUrlError("not a single URL")
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError as exc:
        raise GitHubUrlError("malformed URL") from exc
    if parts.scheme != "https":
        raise GitHubUrlError("only https://github.com URLs are supported")
    if parts.username or parts.password or port not in (None, 443):
        raise GitHubUrlError("the URL must not carry credentials or a port")
    if (parts.hostname or "").lower() not in GITHUB_HOSTS:
        raise GitHubUrlError("only github.com URLs are supported")
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) < 2:
        raise GitHubUrlError("expected https://github.com/<owner>/<repository>")
    owner, repo, rest = segments[0], segments[1], segments[2:]
    check_name(owner, repo)
    if not rest or rest == ["actions"]:
        return GitHubRef(owner, repo)
    if len(rest) >= 3 and rest[0] == "actions" and rest[1] == "runs":
        run_id = _number(rest[2], "run id")
        tail = rest[3:]
        if not tail:
            return GitHubRef(owner, repo, run_id)
        if len(tail) == 2 and tail[0] == "attempts":
            return GitHubRef(owner, repo, run_id, attempt=_number(tail[1], "attempt"))
        if len(tail) == 2 and tail[0] == "job":
            return GitHubRef(owner, repo, run_id, job_id=_number(tail[1], "job id"))
    raise GitHubUrlError("expected a repository, Actions run or job URL")


def safe_url(url: str) -> str:
    """The URL without query string, fragment or userinfo: safe to log or show."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        return "<invalid url>"
    return f"{parts.scheme}://{host}{parts.path}"


def check_log_redirect(location: str | None) -> SplitResult:
    """Validate the single redirect hop of a log download. Raises ``GitHubUrlError``."""
    if not location:
        raise GitHubUrlError("the log redirect has no Location")
    try:
        parts = urlsplit(location)
        port = parts.port
    except ValueError as exc:
        raise GitHubUrlError("malformed log redirect") from exc
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or port not in (None, 443):
        raise GitHubUrlError("the log redirect is not https on port 443")
    if parts.username or parts.password:
        raise GitHubUrlError("the log redirect carries credentials in the host part")
    try:
        ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        raise GitHubUrlError("the log redirect points at an IP address")
    if not any(pattern.match(host) for pattern in LOG_HOST_PATTERNS):
        raise GitHubUrlError(f"the log redirect host {host!r} is not an allowed log store")
    return parts
