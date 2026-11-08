"""GitHub lookup endpoint (M4): what can be investigated at a repository, run or job URL.

Read-only and anonymous unless the owner configured a read-only token (D-031). Every URL is
parsed strictly before any request is made; only https://api.github.com is ever contacted.
"""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status

from kensa.api.deps import SettingsDep
from kensa.api.schemas import (
    GitHubJobOut,
    GitHubLookupIn,
    GitHubLookupOut,
    GitHubRunOut,
    GitHubStepOut,
)
from kensa.core.config import Settings
from kensa.github.client import GitHubClient, GitHubError
from kensa.github.importer import RunInfo, failed_runs, load_run
from kensa.github.urls import GitHubUrlError, parse_github_url

router = APIRouter(tags=["github"])


def github_client(settings: Settings) -> GitHubClient:
    return GitHubClient(
        token=settings.github_token,
        timeout=settings.github_timeout_seconds,
        max_log_bytes=settings.github_max_log_bytes,
    )


def http_error(exc: GitHubError) -> HTTPException:
    return HTTPException(exc.status, exc.message)


def _run_out(run: RunInfo) -> GitHubRunOut:
    data = asdict(run)
    data.pop("status")
    return GitHubRunOut(**data)


@router.post("/github/lookup")
def lookup(body: GitHubLookupIn, settings: SettingsDep) -> GitHubLookupOut:
    try:
        ref = parse_github_url(body.url)
    except GitHubUrlError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    try:
        with github_client(settings) as client:
            common = {
                "owner": ref.owner,
                "repo": ref.repo,
                "html_url": f"https://github.com/{ref.owner}/{ref.repo}",
                "token_configured": client.authenticated,
            }
            if ref.run_id is None:
                runs = failed_runs(client, ref)
                return GitHubLookupOut(
                    kind="repository", runs=[_run_out(r) for r in runs], **common
                )
            _, run, jobs = load_run(client, ref)
    except GitHubError as exc:
        raise http_error(exc) from exc
    selected = next((j.id for j in jobs if j.id == ref.job_id), jobs[0].id if jobs else None)
    return GitHubLookupOut(
        kind="run",
        run=_run_out(run),
        attempt=ref.attempt,
        jobs=[
            GitHubJobOut(
                id=j.id,
                name=j.name,
                conclusion=j.conclusion,
                html_url=j.html_url,
                failed_steps=[GitHubStepOut(**asdict(s)) for s in j.failed_steps],
            )
            for j in jobs
        ],
        selected_job_id=selected,
        **common,
    )
