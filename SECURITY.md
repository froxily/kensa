# Security

> **Status:** threat model and audit completed in M5 (2026-10-30). Findings by severity, with evidence: `eval/reports/m5-security-audit.md`. M6 (2026-11-02) added the replay build and its recorder, covered in the table below.

Kensa is a local, single-operator development tool. It is not designed or hardened for exposure to the internet.

## Principles

1. **Least privilege.** Repository access is read-only. No component holds write-scoped credentials. Future GitHub write actions (for example PR creation) would need a separate, narrowly scoped token and explicit approval for each action.
2. **Untrusted by default.** Uploaded logs, repository files, retrieved text, tool responses, and model output are all data, never instructions. Text reaches the model inside delimited data blocks, and the model has no tools that write.
3. **No execution.** Kensa never executes code, commands, or scripts from repositories, logs, or model output. Remediation diffs are proposals for a human to review.
4. **Secrets stay out.** Known secret patterns (GitHub, AWS, JWT, private keys, connection strings) and high-entropy strings are redacted before storage and before inference. Tokens are never logged, persisted, or sent to the UI.
5. **Loopback only.** PostgreSQL, Ollama, the API, and the dev server bind to 127.0.0.1.
6. **Bounded resources.** Uploads, line counts, download sizes, retries, tool calls, LLM calls, and wall-clock time all have limits.

## Threats addressed

**Already covered by automated tests (M1):**
- secret-redaction corpus, including what must *not* be redacted
- secrets absent from the database, API responses, the prompt and the browser
- prompt injection inside a log, contained by the evidence delimiters and caught by the verifier
- forged `</evidence>` tags
- fabricated citations rejected
- another workspace's data returns 404 on every endpoint
- oversized bodies rejected with 413
- Ollama URL restricted to loopback
- the Ollama probe does not follow redirects

**Added in M3:**
- instruction-like log lines ("ignore previous instructions…") are rejected as citations, and the verifier's retry feedback never repeats evidence text
- a claim must be grounded in the run's own log and shown by its citations
- the database refuses a citation that is both valid and rejected, and a verified report with a rejected citation is refused
- model-proposed edits are dropped when their text is not found exactly once in the file, contains a secret or instruction-like text, or targets a path outside the repository; diffs are computed by Kensa and never applied
- checkpoints are deserialized with LangGraph's strict allowlist, hold only JSON-like state, and are written only while the job lease is held
- LangSmith tracing is forced off in every agent run

**Added in M4 (GitHub integration):**
- **URLs:** strict parsing of user URLs (github.com only, no credentials or ports, validated owner, repository and ids).
- **API access:** pinned to `api.github.com`, GET only. A static test checks that the GitHub package has no write or execute calls and that every request is a literal GET.
- **Log redirects:** one hop only, to `https` on port 443 at an allowlisted log-store host, with no userinfo or IP literals. A chained redirect or a missing `Location` is refused.
- **SSRF:** connections are refused at connect time to private, loopback, link-local, shared, reserved, multicast and IPv4-mapped addresses (no DNS rebinding window).
- **Credentials:**
  - The redirect request carries no `Authorization` and no cookies.
  - The GitHub CLI's OAuth token and any token with OAuth scopes are refused.
  - The token is a secret setting, never logged or returned.
- **Data handling:**
  - Signed log URLs never appear in logs, errors, the database or API responses.
  - Size and time caps apply to every response; archives are refused.
  - Repository file paths from logs are kept inside the run's workspace (no parent, system or dependency paths).
- **No live calls in CI:** every test mocks GitHub, and respx refuses unmocked requests.

**Added in M5:**
- **The operator's browser as an attack path:**
  - **DNS rebinding:** the API answers only `Host: 127.0.0.1` or `localhost` (400 otherwise).
  - **Cross-site requests:** every state-changing request must be `application/json` (415 otherwise), so a cross-site page needs a CORS preflight, which fails.
- **Historical unsafe proposals:** every stored diff was re-checked against the current edit checks. Failures are marked `withdrawn` with a reason, keep their history, and can never be approved.
- **Stored data and traces:** a scan of every stored text column and trace file found no secrets and no signed URLs (`scripts/security_scan.py`, counts only).
- **Telemetry:**
  - traces go to a local, git-ignored file only, with no network exporter
  - spans hold hosts, counts and timings, never full URLs, prompts or log text
- **Prompt-injection corpus:** the instruction-like detector is checked against injections and ordinary CI lines (false positives).
- **CI workflow:** `.github/workflows/ci.yml` is checked by a test: read-only permissions, no secrets, no `pull_request_target`, no persisted checkout credentials, mock inference only.

## Threat model (M5)

**Assets:**
- the owner's logs and repository content (which may contain secrets)
- the GitHub token, when configured
- investigation records and approval decisions
- the owner's machine (nothing is ever executed)

**Adversaries and entry points:**

| Adversary | Entry point | What they control |
|---|---|---|
| Author of CI output or repository content (for example a pull request from a fork) | Logs, workflow files, source files, retrieved incidents; commit messages and diff hunks (v1.1) | Every line of evidence, including forged error lines and injected instructions |
| A web page open in the operator's browser | The browser can reach 127.0.0.1 | DNS answers for its own domain; cross-site requests |
| A hostile network or DNS | GitHub log redirects, name resolution | Redirect targets and resolved addresses |
| The model | Structured output | Diagnoses, citations, proposed edits |

**Out of scope:** other processes running as the same OS user (they can read `.env` and the database directly), physical access, and any networked or multi-user deployment.


| Threat | Mitigation |
|---|---|
| Prompt injection | Delimited untrusted text; schema-validated outputs; a deterministic citation verifier; no write tools for the model |
| Secret leakage | Redaction at ingestion and before inference; log scrubbing |
| SSRF | Fixed `api.github.com` host; strict URL parsing; manual, allowlisted, credential-free redirect handling; private-address rejection |
| Path traversal | User filenames never touch disk; diff target paths validated; archives are refused, never unpacked (D-032) |
| Resource exhaustion | Size, time, and count limits; leased job worker with bounded retries |
| Cross-workspace access | Server-side, workspace-scoped authorization on every query |
| DNS rebinding and CSRF from the operator's browser | Trusted `Host` values only; JSON-only state changes; CORS limited to the UI origin |
| Unsafe or wrong remediation | Read-only proposals; mechanical edit checks; withdrawal of unsafe records; a human decision. Proposals are never shown to be semantically correct |
| Leakage through traces or stored records | No network exporter; no URLs, prompts or log text in spans; stored-data scan |
| A forged or misleading change history (v1.1) | Change analysis reads the compare API at import only, within a request budget. Unknown comparability factors are never treated as "same". Suspects are `correlated` or `weak` (a CHECK constraint); diff hunks are redacted, wrapped as data, and can support a claim but never corroborate it |
| History confirming itself (v1.1, D-051) | Model conclusions are no longer indexed as evidence (`index_incidents` off). Fingerprints are rule-derived. Similar failures and confirmed resolutions are shown apart from the evidence and never change a verification status (tested). A false recurrence claim could still mislead a reader, so history matching is off by default since v1.1.0 (D-057), and only an exact fingerprint may claim a recurrence |
| Data kept after the owner asks to forget it (v1.1) | Forget repository and retention delete whole investigations with every derived record, LangGraph checkpoints, fingerprint links, change analyses, diff documents and analytics rows; a meta-test fails if a table with `workspace_id` is not covered; only counts remain in `purge_audits` |
| Personal data in history (v1.1) | Commit authors, e-mail addresses and actor logins are never stored |
| Request floods against GitHub (v1.1) | Per-sync and per-import request budgets; one active sync per repository; a rate limit ends the batch and nothing reschedules itself |
| Leakage through the published replay (M6) | The recorder uses its own database and refuses to write if any recorded string matches the secret, signed-URL or local-path checks; the replay build makes no request outside its own files (tested) |

## Reporting

This is currently a private, local project. A reporting channel will be added if it is ever published.
