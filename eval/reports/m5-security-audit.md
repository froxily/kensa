# M5 security audit

> 2026-10-30. Scope: the local Kensa stack (FastAPI backend, React UI, PostgreSQL, Ollama, the GitHub integration, the agent workflow and its stored records). The method was code review, targeted probes and automated tests. Every claim below is backed by a test (`backend/tests/…`) or by the command output recorded during the audit. The owner's GitHub token was not used.

## Findings by severity

| ID | Severity | Status | Finding |
|---|---|---|---|
| M5-1 | Medium | **Fixed** (D-035) | The API answered any `Host` header (probe: `Host: evil.example` returned 200). A malicious web page could use **DNS rebinding** to point its own domain at 127.0.0.1, then read investigations and logs, approve or reject proposals, and trigger GitHub lookups (with the token, if configured) from the owner's browser. `TrustedHostMiddleware` now accepts only `127.0.0.1` and `localhost`; others get 400 (`test_unknown_host_headers_are_refused`). |
| M5-2 | Low | **Fixed** (D-035) | **CSRF on body-less POSTs.** A cross-site "simple" request (form post or no-cors fetch) to `POST /api/investigations/{id}/retry` would have been executed. JSON-bodied endpoints already refused `text/plain` (422). Impact was limited (it needs the investigation's UUID; it re-queues a failed run). Now every state-changing request must be `application/json` (415 otherwise), so a cross-site request needs a CORS preflight, which fails (`test_cross_site_simple_requests_cannot_change_anything`, 16 cases). |
| M4-L1 | High (at the time) | **Fixed in M4; records remediated in M5** (D-030, D-036) | Model-proposed edits that deleted keys or printed a secret-backed variable were shown as "validated" diffs. M4 added the structural checks. M5 re-checked every stored diff (`scripts/withdraw_unsafe_proposals.py`): exactly the two known diffs fail. Their investigations' proposals (`6efb4773…`, `93616176…`) are withdrawn as unsafe or non-actionable, with history kept, and can never be approved (`test_withdrawal.py`). |
| A-1 | Low | Accepted (by design) | **No authentication on the local API.** Single operator, bound to 127.0.0.1. Mitigated by trusted hosts, CORS limited to the UI origin, JSON-only state changes, and workspace scoping on every query. Revisit before any shared or networked deployment. |
| A-2 | Low | Accepted (inherent) | **Prompt injection.** The instruction-like detector is a heuristic (corpus: 8/8 injections caught, 0/8 false positives on ordinary CI lines; `test_security.py`). Logs are attacker-controllable evidence: a forged error line is indistinguishable from a real one. Containment: evidence is delimited, the model has no tools, citations are verified deterministically, instruction-like lines are never evidence, remediation is read-only and needs a human decision. |
| A-3 | Low | Accepted | **The GitHub token sits in plaintext in the git-ignored `.env`** (standard for local tools). It is fine-grained, scoped to one repository, read-only, with a short expiry. Kensa refuses the CLI login token and any token with OAuth scopes. It is never in responses, logs, the database or traces (`test_the_token_never_appears_in_responses_or_logs`). Recommendation: revoke it after use. |
| A-4 | Low | Accepted | **Remediation diffs are checked mechanically only** (they parse; existing keys are kept; workflow steps stay runnable; shell constructs balance; no printed secrets). They are **not** shown to be semantically correct or safe, and are never applied. |
| A-5 | Low | Open (recommendation) | **No per-client rate limiting** on the local API, and no cap on the number of stored investigations (disk growth). Acceptable for a single local operator. |
| A-6 | Info | **Closed in M5.1** (D-043) | **Dependency vulnerability scanning**, run after the owner approved it: `pip-audit` 2.10.1 (via `uvx`, not added to the project) found no known vulnerabilities in the 82 pinned backend packages (PyPI advisory data and OSV); `npm audit` found 0 in the 303 frontend packages. Nothing needed upgrading. |
| A-7 | Info | Accepted | **Ollama has no authentication** (any local process can use it); it listens on 127.0.0.1 only. |
| A-8 | Info | Open (before any publication) | **The CI workflow references third-party actions by major tag** (`actions/checkout@v4`, `actions/setup-node@v4`, `astral-sh/setup-uv@v6`), not by commit SHA. A moved tag could change what runs. It has no effect while the repository is private, because the workflow never runs. Pin each action to a full SHA before publishing. The workflow's permissions are already read-only, it uses no secrets, and checkout credentials are not persisted (`test_ci_workflow.py`). |

No High or Critical finding is open.

## Areas verified (no finding)
- **Secret redaction:**
  - **Before storage and inference:** the corpus tests pass, including the fine-grained `github_pat_`, classic `ghp_` and OAuth `gho_` formats (probe: all three redacted).
  - **Stored data:** `scripts/security_scan.py` scanned 837 stored values in 7 tables (documents, chunks, events, diagnoses, citations, proposals and diffs, run records) plus the trace files. It found **0 secrets and 0 signed log URLs**.
  - **After the held-out run:** the scan was repeated over the main database (837 values) and the evaluation database (5,044 values across the same tables), plus all 4 trace files including both M5 evaluation runs. It again found **0 secrets and 0 signed log URLs**.
- **SSRF and redirects** (`test_github.py`):
  - **Hosts:** only `api.github.com`, GET only, plus one validated redirect hop to an allowlisted log store. The store host was confirmed in the M4 live run.
  - **Connections:** private, loopback, link-local, reserved and IPv4-mapped addresses are refused at connect time. The redirect hop carries no `Authorization` and no cookies.
  - **Environment:** clients use `trust_env=False` (no proxies or `.netrc`). The Ollama URL must be a loopback address.
- **Authorization:** every endpoint returns 404 for another workspace's investigation (events, stream, documents, retry, and now the decision endpoint: `test_another_workspaces_proposals_cannot_be_decided`).
- **Resource limits:**
  - **Requests:** request bodies up to 2.5 MB (413 beyond), logs up to 2 MB and 50,000 lines.
  - **GitHub:** JSON up to 3 MB, logs up to 16 MB, at most 6 files of 200 KB each.
  - **Agent:** per-run budgets (3 diagnoses, 2 retrieval rounds, 4 model calls, 900 s), job retries capped at 3.
  - **Streaming and lists:** live streams end after 600 s; page sizes are capped at 100 and event batches at 500.
- **Traces and logs:** no network exporter, and no full URLs from GitHub or Ollama calls (`test_telemetry.py`). Model-call spans hold counts and timings, never prompt text.
- **Frontend:** no `dangerouslySetInnerHTML`; diffs and logs render as text; external links use `rel="noopener noreferrer"`. The Vite 8.3.5 dev server blocks unknown hosts by default.
- **CI workflow** (`.github/workflows/ci.yml`, never run): it mirrors all 11 local checks, with `contents: read`, no secrets, no `pull_request_target`, mock inference only (`test_ci_workflow.py`).
- **Never executed:** nothing downloaded or proposed is ever run. A static test checks that the GitHub package has no write or exec calls, and edits are parsed only.

## Not covered
- No penetration test by a third party, and no fuzzing.
- Dependency scans are a point-in-time result (M5.1, 2026-10-30); repeat them before any publication.
- The CI workflow has never run on GitHub. It is checked by tests and by YAML parsing, not by GitHub's workflow schema (`check-jsonschema` is not installed).
- The audit covers the local, single-user deployment only.
