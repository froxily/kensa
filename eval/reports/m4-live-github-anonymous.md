# M4 live check: real GitHub, anonymous access

> Real requests to api.github.com on 2026-10-30, read-only and without a token. The full live investigation of a real failed run, which needs the job log and therefore a token, has **not** been run yet. See "Not verified" below.

- **Date (UTC):** 2026-10-30 12:56 · **Git:** `5a1b6ac` · **Access:** anonymous (no `KENSA_GITHUB_TOKEN`)
- **Run used:** https://github.com/pytest-dev/pytest/actions/runs/40653773395/job/122700520033 (a public repository; a genuine failed `pull_request` run from 2026-10-28)

## Probe of GitHub's behaviour (direct GETs, before the design was fixed)

| Request | Result |
|---|---|
| `GET /repos/pytest-dev/pytest/actions/runs?status=failure&per_page=5` | 200; 5 recent failed runs; anonymous limit `X-RateLimit-Limit: 60` |
| `GET .../actions/runs/40653773395/jobs?filter=latest&per_page=100` | 200; 32 jobs, 20 failed. The failed steps come from GitHub's step conclusions (e.g. step 7 "Test with coverage") |
| `GET .../actions/jobs/122700520033/logs` | **403** `"Must have admin rights to Repository."`: anonymous job-log downloads are refused even for public repositories |
| `GET .../check-runs/122700520033/annotations` | 200; only "Process completed with exit code 1." and a runner notice, which is not enough to diagnose |

## Through Kensa's API (in-process, real network, token removed)

| Step | Result |
|---|---|
| `POST /api/github/lookup` with the job URL | 200, `kind: run`. Run 40653773395 "test" #11791, conclusion `failure`, commit `9d4f2a3`, `.github/workflows/test.yml`. 20 failed jobs; the selected job "build (ubuntu-py312)" has failed step "Test with coverage" |
| `POST /api/github/lookup` with the repository URL | 200, `kind: repository`, 10 recent failed runs |
| `POST /api/investigations` (source `github`, no token, no pasted log) | **403** with "GitHub only serves job logs to signed-in requests, even for public repositories. Add a read-only KENSA_GITHUB_TOKEN, or paste the job's log." Nothing was stored |

## Not verified (needs the owner's read-only token)
- Downloading a real job log through GitHub's `302` redirect. This includes confirming that the real log-store host is in Kensa's allowlist (D-032). An unknown host fails closed.
- A complete investigation of a real failed run: import, diagnosis by the local model, citations and commit-pinned evidence on real data.

Run it once the token is in `.env`:

```
uv run --directory backend --no-sync python ../scripts/github_live_check.py https://github.com/pytest-dev/pytest/actions/runs/40653773395/job/122700520033
```

It writes its own report. The authenticated run made later (2026-10-30) used one of the owner's public repositories; that report holds the repository's real logs and is not published.
