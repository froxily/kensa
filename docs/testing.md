# Testing and CI

Everything below runs locally with one command, installs nothing and calls no paid or remote
service:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ci-local.ps1
```

It needs the Compose database (`docker compose up -d db`). Without it, the database tests are
skipped with a reason, and the run must not be counted as a pass. Check that the summary shows
**0 skipped**.

## The steps

| Step | What it checks |
|---|---|
| backend: ruff check, ruff format | Lint and formatting of `backend/` and `scripts/` |
| backend: mypy | `mypy --strict` over the backend, its tests and `scripts/` |
| backend: pytest | Unit, API, database and agent tests (below) |
| frontend: eslint, prettier, typecheck | TypeScript in strict mode, the React hooks rules, formatting |
| frontend: vitest | Components and hooks against a mocked API; the locale catalogues; date formats per language; the replay adapter |
| frontend: build | The production build |
| frontend: e2e + axe | Playwright against the real app and against the replay build (below) |
| infra: compose config | `docker-compose.yml` validates |

## Backend tests
The model is never called in tests: the deterministic mock provider stands in for Ollama, and
recorded HTTP fixtures (respx) stand in for GitHub. Areas with the most tests:

- **The agent graph** (`test_agent.py`):
  - checkpoints, and resuming after a worker is killed mid-run
  - bounded retries
  - the approval interrupt, with idempotent and conflicting decisions
  - prompt injection in logs
  - malformed model output
- **The verifier** (`test_verifier.py`, `test_causes.py`): citation checks, the root-cause statuses, and the rule that a failing assertion never corroborates a cause (D-046).
- **The job worker** (`test_jobs.py`): leases, heartbeats, crash recovery, fencing of stale workers, and duplicate enqueues.
- **GitHub import** (`test_github*.py`):
  - URL parsing and the read-only client
  - the single allowlisted log redirect, with no credentials, rejecting private addresses and DNS rebinding
  - typed timeouts and size limits
- **Security:**
  - `test_security.py`: the prompt-injection corpus, Host checks, cross-site requests, and workspace authorisation, plus the token never appearing in responses or logs.
  - `test_redaction.py`: secret redaction.
  - `test_remediation.py`: diff path traversal.
  - `test_api_investigations.py`: oversized input and workspace isolation.
- **The evaluation harness** (`test_evaluation.py`): dataset freezing and the metrics.
- **The replay recording** (`test_replay_recording.py`, `test_record_replays.py`):
  - written without Kensa's verifier, it checks every recorded log line, evidence block, error signature and citation (all 20) against the sample logs, the knowledge notes and the v2 dev cases
  - it fails if the recording is edited by hand: altered quotes, evidence lines and statuses were each caught when tried
  - the recorder refuses to write secrets, signed URLs or this machine's paths
- **The repository** (`test_repository.py`): nothing the app or its evaluation reads is git-ignored.

Tests marked `db` use the local PostgreSQL. Each creates its own data, so they never touch the development database.

## End-to-end tests (`frontend/e2e/`)
`npx playwright test` starts three servers, each bound to 127.0.0.1:

| Server | Port | What it is |
|---|---|---|
| `scripts/e2e_server.py` | 8010 | The real backend, rules-only provider, its own `kensa_e2e` database |
| `vite` dev server | 5174 | The real frontend, proxying `/api` to 8010 |
| `vite preview --mode replay` | 4174 | The static replay build, with no proxy at all |

- **`investigation.spec.ts`:**
  - a sample investigation end to end, through to the citation that opens its log line
  - redaction of a pasted secret
  - the skip link
  - axe on the main pages in **English and Japanese, light and dark**
- **`replay.spec.ts`** (also runs alone, with no backend, database or model: `npm --prefix frontend run e2e:replay`):
  - the replay build shows the recorded runs, labelled as a replay, and makes **no request outside its own files** (every request is recorded and checked)
  - every page, a citation, an approval and the language switch still work with **every request outside the replay's own files blocked**, with no page or console errors
  - before a decision, the approve and reject buttons carry the note that a decision is temporary; after it, "Not saved"; a reload discards it
  - **keyboard only:** the skip link, the language select (changed with the arrow keys), an investigation link, a citation and the approval, each reached with Tab and showing a focus outline
  - **phone width (375 px), English and Japanese:** no page scrolls sideways (log lines scroll inside their own box), and axe passes
  - axe in both languages and themes
- **Accessibility bar:** zero serious or critical axe violations (WCAG 2.1 A and AA tags).

## Release checks (manual, run for M6)
| Check | Command |
|---|---|
| The recording is exactly what Kensa stored for those runs | `uv run --directory backend --no-sync python ../scripts/record_replays.py --verify` (needs the Compose database, not the model) |
| Screenshots, captioned video, caption files and transcript | `npm --prefix frontend run media` (Windows: re-encodes with Playwright's cached ffmpeg) |
| Third-party notices | `uv run --directory backend --no-sync python ../scripts/third_party_notices.py` |
| The replay with the database, Ollama and the backend stopped | `docker compose stop db`, quit Ollama, then `npm --prefix frontend run e2e:replay` |
| The deployed demo passes the same 10 replay tests | `$env:KENSA_REPLAY_URL = "https://froxily.github.io/kensa/"; npm --prefix frontend run e2e:replay` (no local server is started) |

## Fresh-clone check (manual, before any publication)
This catches what CI cannot: files that exist locally but are not in git. In M6 it found that the sample logs had never been committed.
1. Run `git clone` of the repository into a new folder.
2. Follow README "Run it locally" exactly, with **Rules only**.
3. Check that a sample investigation finishes and shows its report.

On a machine that already runs Kensa's database, give the clone's database its own Compose project (`docker compose -p kensa-fresh up -d db`). `docker-compose.yml` fixes the project name, so a second checkout would otherwise reuse the first one's container and volume. `backend/tests/test_repository.py` guards the git side of this in CI.

## What CI does not cover
- **The live model.** Live runs are measured separately:
  - `scripts/live_check.py`
  - the evaluation harness (`scripts/evaluate.py`, see [evaluation.md](evaluation.md))
  - the replay recorder (`scripts/record_replays.py`)
- **Live GitHub.** The client is tested against recorded fixtures. M4's anonymous live check is in `eval/reports/m4-live-github-anonymous.md`. The authenticated run's reports hold a real repository's logs and are not published.
- **The GitHub Actions workflow** (`.github/workflows/ci.yml`) mirrors these steps.
  - `backend/tests/test_ci_workflow.py` verifies it: least privilege, no secrets, the mock provider, the same steps.
  - It has never run on GitHub, because the repository is not published.
  - Its actions are pinned by tag; pinning by commit SHA is a pre-publication item.
