"""Read-only GitHub REST client pinned to https://api.github.com (M4, D-031, D-032).

* GET only. There is no method that writes, and ``_get`` refuses any path outside ``/repos/``.
* Anonymous by default. An optional fine-grained token (``KENSA_GITHUB_TOKEN``) is sent only to
  api.github.com, never on the log-download redirect, and never logged, stored or returned.
  A classic token that carries OAuth scopes is refused at first use, because Kensa must only
  ever hold read-only access.
* Conditional requests: an in-process ETag cache answers repeated lookups with ``304 Not
  Modified``, which saves the anonymous budget of 60 requests per hour.
* Bounded: every response is read as a stream with a size cap and a wall-clock deadline.
* Errors become ``GitHubError`` with a stable code and a message safe to show; signed log URLs
  never appear in them.
"""

import json
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode

import httpcore
import httpx
import structlog
from pydantic import SecretStr

from kensa import __version__
from kensa.core.telemetry import set_span_attributes, traced
from kensa.github.net import PrivateAddressError, build_client
from kensa.github.urls import GitHubUrlError, check_log_redirect, check_name, safe_url

logger = structlog.get_logger(__name__)

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
USER_AGENT = f"kensa/{__version__} (local; read-only)"
MAX_JSON_BYTES = 3_000_000
CACHE_ENTRIES = 256
REDIRECTS = frozenset({301, 302, 303, 307, 308})
# Tokens that must never be used: OAuth app, user-to-server, server and refresh tokens (the
# GitHub CLI's own login token is an OAuth token, "gho_...").
FORBIDDEN_TOKEN_PREFIXES = ("gho_", "ghu_", "ghs_", "ghr_")


class GitHubError(Exception):
    """``code`` is stable; ``status`` is the HTTP status Kensa's API answers with."""

    def __init__(
        self, code: str, message: str, status: int = 502, retry_at: datetime | None = None
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.status, self.retry_at = code, message, status, retry_at


@dataclass(frozen=True)
class LogDownload:
    content: bytes
    via_redirect: bool
    host: str


class ETagCache:
    """Bounded LRU of ``url -> (etag, parsed body)`` shared by the clients of one process."""

    def __init__(self, size: int = CACHE_ENTRIES) -> None:
        self._size = size
        self._items: OrderedDict[str, tuple[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> tuple[str, Any] | None:
        with self._lock:
            item = self._items.get(key)
            if item is not None:
                self._items.move_to_end(key)
            return item

    def remember(self, key: str, etag: str, body: Any) -> None:
        with self._lock:
            self._items[key] = (etag, body)
            self._items.move_to_end(key)
            while len(self._items) > self._size:
                self._items.popitem(last=False)


SHARED_CACHE = ETagCache()


def _refused_address(exc: BaseException) -> bool:
    """httpx wraps transport errors; look through the chain for the address refusal."""
    seen: BaseException | None = exc
    while seen is not None:
        if isinstance(seen, PrivateAddressError):
            return True
        seen = seen.__cause__ or seen.__context__
    return False


def _read_capped(response: httpx.Response, limit: int, deadline: float) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > limit:
            raise GitHubError(
                "response_too_large", f"GitHub's response exceeded {limit // 1_000_000} MB."
            )
        if time.monotonic() > deadline:
            raise GitHubError("timeout", "GitHub did not finish answering in time.", 504)
        chunks.append(chunk)
    return b"".join(chunks)


def _message(body: bytes) -> str:
    try:
        text = str(json.loads(body).get("message", ""))
    except (ValueError, AttributeError):
        text = ""
    return text[:200]


def _rate_limit_error(response: httpx.Response, message: str) -> GitHubError | None:
    remaining = response.headers.get("x-ratelimit-remaining")
    retry_after = response.headers.get("retry-after")
    limited = (
        response.status_code == 429
        or remaining == "0"
        or retry_after is not None
        or "rate limit" in message.lower()
    )
    if not limited:
        return None
    retry_at: datetime | None = None
    if retry_after is not None and retry_after.isdigit():
        retry_at = datetime.fromtimestamp(time.time() + int(retry_after), UTC)
    elif (reset := response.headers.get("x-ratelimit-reset", "")).isdigit():
        retry_at = datetime.fromtimestamp(int(reset), UTC)
    when = f" after {retry_at:%H:%M} UTC" if retry_at else " later"
    return GitHubError(
        "rate_limited",
        f"GitHub's API rate limit is used up (anonymous access allows 60 requests per hour). "
        f"Try again{when}.",
        429,
        retry_at,
    )


def error_for(response: httpx.Response, body: bytes, *, what: str) -> GitHubError:
    message = _message(body)
    if response.status_code in (403, 429):
        limited = _rate_limit_error(response, message)
        if limited is not None:
            return limited
    if response.status_code == 401:
        return GitHubError(
            "token_rejected",
            "GitHub rejected the configured token (expired or revoked). Replace or remove "
            "KENSA_GITHUB_TOKEN.",
            502,
        )
    if response.status_code == 403:
        return GitHubError("forbidden", f"GitHub refused access to {what}: {message}", 403)
    if response.status_code == 404:
        return GitHubError("not_found", f"GitHub has no {what}, or it is not public.", 404)
    if response.status_code == 410:
        return GitHubError("gone", f"GitHub no longer has {what}.", 410)
    return GitHubError("upstream_error", f"GitHub answered {response.status_code} for {what}.", 502)


class GitHubClient:
    def __init__(
        self,
        *,
        token: SecretStr | None = None,
        timeout: float = 20.0,
        max_log_bytes: int = 16_000_000,
        cache: ETagCache | None = None,
        network: httpcore.NetworkBackend | None = None,
    ) -> None:
        if token is not None and token.get_secret_value().startswith(FORBIDDEN_TOKEN_PREFIXES):
            raise GitHubError(
                "token_refused",
                "KENSA_GITHUB_TOKEN is an OAuth or app token (for example the GitHub CLI's "
                "login). Kensa only accepts a read-only personal access token.",
                500,
            )
        self._token = token
        self._timeout = timeout
        self._max_log_bytes = max_log_bytes
        self._cache = cache if cache is not None else SHARED_CACHE
        self._network = network
        self._api = build_client(
            timeout=timeout,
            backend=network,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": USER_AGENT,
            },
        )

    @property
    def authenticated(self) -> bool:
        return self._token is not None

    def close(self) -> None:
        self._api.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _auth(self) -> dict[str, str]:
        if self._token is None:
            return {}
        return {"Authorization": f"Bearer {self._token.get_secret_value()}"}

    def _check_scopes(self, response: httpx.Response) -> None:
        scopes = response.headers.get("x-oauth-scopes", "").strip()
        if self._token is not None and scopes:
            raise GitHubError(
                "token_refused",
                "KENSA_GITHUB_TOKEN carries OAuth scopes. Kensa only uses a token without "
                "write access: create a fine-grained token limited to public repositories.",
                500,
            )

    @staticmethod
    def _url(path: str, params: dict[str, str | int] | None) -> str:
        # No "." or ".." path segment (v1.1: a segment may contain dots, as in GitHub's
        # compare/<base>...<head>; every caller builds paths from validated names and ids).
        segments = path.split("/")
        if not path.startswith("/repos/") or any(s in (".", "..") for s in segments):
            raise GitHubError("invalid_request", "Kensa only reads repository data.", 500)
        query = f"?{urlencode(sorted((params or {}).items()))}" if params else ""
        return f"{API_ROOT}{path}{query}"

    @contextmanager
    def _stream(self, url: str, headers: dict[str, str]) -> Iterator[httpx.Response]:
        try:
            with self._api.stream("GET", url, headers=headers) as response:
                yield response
        except httpx.TimeoutException as exc:
            raise GitHubError("timeout", "GitHub did not answer in time.", 504) from exc
        except httpx.HTTPError as exc:
            if _refused_address(exc):
                raise GitHubError(
                    "network_refused", "api.github.com resolved to a non-public address."
                ) from exc
            raise GitHubError("upstream_error", "Could not reach GitHub.", 502) from exc

    @traced("github.request")
    def get_json(self, path: str, params: dict[str, str | int] | None = None, *, what: str) -> Any:
        url = self._url(path, params)
        cached = self._cache.get(url)
        headers = self._auth()
        if cached is not None:
            headers["If-None-Match"] = cached[0]
        deadline = time.monotonic() + self._timeout * 2
        with self._stream(url, headers) as response:
            self._check_scopes(response)
            body = _read_capped(response, MAX_JSON_BYTES, deadline)
            logger.info(
                "github_request",
                path=path,
                status=response.status_code,
                remaining=response.headers.get("x-ratelimit-remaining"),
            )
            set_span_attributes(
                github_path=path,
                status=response.status_code,
                rate_remaining=response.headers.get("x-ratelimit-remaining"),
                cached=response.status_code == 304,
            )
            if response.status_code == 304 and cached is not None:
                return cached[1]
            if response.status_code != 200:
                raise error_for(response, body, what=what)
            try:
                parsed = json.loads(body)
            except ValueError as exc:
                raise GitHubError(
                    "upstream_error", f"GitHub sent invalid JSON for {what}."
                ) from exc
            etag = response.headers.get("etag")
            if etag:
                self._cache.remember(url, etag, parsed)
            return parsed

    @traced("github.job_log")
    def job_log(self, owner: str, repo: str, job_id: int) -> LogDownload:
        """Download one job's plain-text log, following GitHub's redirect exactly once."""
        check_name(owner, repo)
        url = self._url(f"/repos/{owner}/{repo}/actions/jobs/{int(job_id)}/logs", None)
        deadline = time.monotonic() + self._timeout * 3
        location: str | None = None
        body = b""
        with self._stream(url, self._auth()) as response:
            self._check_scopes(response)
            status = response.status_code
            if status in REDIRECTS:
                location = response.headers.get("location")
            else:
                body = _read_capped(response, self._max_log_bytes, deadline)
        logger.info("github_job_log", job_id=job_id, status=status)
        set_span_attributes(github_job_id=job_id, status=status)
        if status == 200:
            return LogDownload(body, via_redirect=False, host="api.github.com")
        if status not in REDIRECTS:
            if status == 403 and not self.authenticated and "admin rights" in _message(body):
                raise GitHubError(
                    "logs_need_token",
                    "GitHub only serves job logs to signed-in requests, even for public "
                    "repositories. Add a read-only KENSA_GITHUB_TOKEN, or paste the job's log.",
                    403,
                )
            if status in (404, 410):
                raise GitHubError(
                    "logs_unavailable",
                    "GitHub no longer has this job's log (logs expire, or were deleted). "
                    "Paste the log if you still have it.",
                    410,
                )
            raise error_for(response, body, what="this job's log")
        try:
            target = check_log_redirect(location)
        except GitHubUrlError as exc:
            logger.warning("github_log_redirect_refused", reason=str(exc))
            raise GitHubError("redirect_refused", f"Refused the log download: {exc}.") from exc
        return self._download(target.geturl(), deadline)

    @traced("github.log_download")
    def _download(self, url: str, deadline: float) -> LogDownload:
        """The redirect hop: a fresh client with no Authorization header, no cookies and no
        further redirects."""
        host = safe_url(url)
        try:
            with (
                build_client(
                    timeout=self._timeout,
                    headers={"User-Agent": USER_AGENT},
                    backend=self._network,
                ) as client,
                client.stream("GET", url) as response,
            ):
                if response.status_code in REDIRECTS:
                    raise GitHubError("redirect_refused", "The log store redirected again.")
                if response.status_code != 200:
                    raise GitHubError(
                        "logs_unavailable",
                        f"The log store answered {response.status_code}; the signed link "
                        "may have expired. Try again.",
                        502,
                    )
                content_type = response.headers.get("content-type", "").lower()
                if "zip" in content_type:
                    raise GitHubError("unsupported_content", "The log arrived as an archive.")
                body = _read_capped(response, self._max_log_bytes, deadline)
        except httpx.TimeoutException as exc:
            raise GitHubError("timeout", "The log download timed out.", 504) from exc
        except httpx.HTTPError as exc:
            if _refused_address(exc):
                raise GitHubError(
                    "redirect_refused", "The log store resolved to a non-public address."
                ) from exc
            raise GitHubError("upstream_error", "The log download failed.") from exc
        if body.startswith(b"PK\x03\x04"):
            raise GitHubError("unsupported_content", "The log arrived as an archive.")
        logger.info("github_log_downloaded", store=host, bytes=len(body))
        set_span_attributes(log_store=host.split("/")[2], bytes=len(body))
        return LogDownload(body, via_redirect=True, host=host.split("/")[2])

    def file_at(self, owner: str, repo: str, path: str, ref: str) -> dict[str, Any] | None:
        """A repository file's metadata and base64 content at a commit, or None if absent."""
        check_name(owner, repo)
        quoted = quote(path, safe="/")
        try:
            data = self.get_json(
                f"/repos/{owner}/{repo}/contents/{quoted}", {"ref": ref}, what=f"file {path}"
            )
        except GitHubError as exc:
            if exc.code in ("not_found", "gone"):
                return None
            raise
        return data if isinstance(data, dict) else None
