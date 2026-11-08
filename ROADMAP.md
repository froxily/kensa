# ROADMAP

**Status key:** `[ ]` not started · `[~]` in progress · `[x]` done and verified · `[c]` conditionally approved by the owner, with unmet items listed

MVP = M0 + M1. Nothing from M2 onwards starts until every M1 acceptance item is checked.

---

## M0: Environment and foundation `[x]` (completed 2026-10-30)

**Objective:** a verified toolchain, the primary model benchmarked, and a working skeleton.

- [x] Prerequisite audit (read-only), 2026-10-29
- [x] Docker engine running (Docker 29.8.0)
- [x] Ollama installed (0.40.13, listening on 127.0.0.1:11434 only, no `OLLAMA_*` vars)
- [x] Root docs
- [x] Local git repo (no remote) with a repo-local identity
- [x] `docker compose up -d db` healthy (PostgreSQL 18.6), published on 127.0.0.1:5433 only, 1 GiB limit
- [x] Backend skeleton: live `/api/health` returned `status: ok` (DB ok, pgvector 0.8.7, model ok); ruff, mypy, and pytest green
- [x] Alembic baseline applied to the real DB; up/down/up round-trip test passes
- [x] Frontend skeleton: lint, tsc, vitest, and build green; dark mode; health indicator
- [x] `scripts/ci-local.ps1` runs every check, exit 0 (backend 37 passed, 0 skipped)
- [x] `qwen3:4b-instruct-2507-q4_K_M` pulled and benchmarked; reports hold real measured numbers
- [x] Inference options chosen from measurements: `num_ctx=8192`, `num_gpu=99` (D-009)

## M1: Functional MVP `[x]` (completed 2026-10-30)

**Objective:** paste or upload a log, get a cited diagnosis from local Ollama, end to end.

- [x] Upload/paste API with size/line caps (413 before parsing); secret redaction before storage and before the LLM
- [x] Log parser, chunkers, error-signature extraction, rule classifier (8 categories)
- [x] FTS + signature retrieval (RRF fusion, tail fallback, workspace-scoped)
- [x] Structured diagnosis (Pydantic) with cited evidence IDs, lines and quotes; deterministic citation verifier (D-018)
- [x] Pipeline nodes are pure functions over `InvestigationState` (ready for LangGraph in M3)
- [x] Leased Postgres job worker: leases, heartbeat, crash recovery, bounded retries, idempotency keys, fencing
- [x] `agent_events` with SSE progress (resumable); provider switch (Ollama/mock); typed error states
- [x] UI: Overview, New Investigation (paste/upload + 3 samples), Workspace (timeline, evidence), Report (citations jump to highlighted lines)
- [x] Loading, error, empty, and model-unavailable states; keyboard accessible; centralized strings
- [x] One sample incident runs end to end with **live Ollama**, and all citations pass the verifier: all 3 samples plus a long log, each verified with 4/4 citations (`eval/reports/m1-live-check.md`, commit 673da48)
- [x] The same run passes with the mock provider (API tests and Playwright E2E)
- [x] Worker tests: no double processing by concurrent workers; a killed worker's job is reclaimed and completes once; retries stop at max; duplicate enqueue gives one job; a stale worker's completion is rejected
- [x] Unit, API, DB, and component tests plus Playwright E2E pass: backend 150, vitest 18, e2e 5
- [x] axe: no critical violations on main pages. The test is stricter: zero serious or critical, light and dark

## M2: Advanced RAG `[c]` (implemented 2026-10-30; conditionally approved by the owner 2026-10-30)

**Unmet, and not claimed as achieved:**
- **Hybrid retrieval is not better than full text.** On the dev split, full text alone has the best Recall@5/@10, and hybrid is level with M1. Full text stays the baseline that every later retrieval change is compared against (D-027).
- **Not every generated citation is valid.** 88% (M1) and 93% (hybrid) of LLM citations on dev are valid. Every invalid citation is rejected; M3 must make sure none can ever be accepted or presented as verified evidence.


- [x] `qwen3-embedding:0.6b` downloaded with approval; placement measured: CPU 0.8 vs GPU 41.3 chunks/s, so GPU with sequential model swap (D-024)
- [x] pgvector HNSW, weighted RRF fusion (weights fixed before evaluation, D-023), code/YAML/Markdown chunkers, incremental re-index by hash, repositories and scoped documents (D-022), knowledge notes, verified incidents (D-026)
- [x] Evaluation dataset v1: 40 cases (20 dev / 20 test), labels set at authoring time, frozen before any evaluation (`207bde74cb9585d4`). Written by a separate LLM author, isolated from Kensa's code, rather than by hand (D-025); the first, templated attempt was rejected
- [x] Recall@5/@10 and MRR per channel and fused on the dev split; hybrid vs FTS reported as measured: **hybrid ≈ M1, and FTS alone scored highest** (`eval/reports/m2-retrieval-dev-ollama.md`)
- [x] Ingestion idempotency tested (unchanged files skipped, changed re-chunked, vanished removed)
- [ ] Every eval citation valid: **not met as written.** 68/77 (M1) and 74/80 (hybrid) LLM citations are valid on dev. Every invalid one is rejected and shown as rejected, never presented as evidence (`eval/reports/m2-diagnosis-dev-ollama.md`)
- Diagnosis on dev (end to end): rules-only 15/20, LLM + M1 retrieval 16/20, LLM + hybrid 17/20. Test split untouched (M5)
- `ci-local.ps1`: all 11 steps pass (backend 181, vitest 19, e2e 5 with axe)

## M3: Agentic investigation `[c]` (approved by the owner 2026-10-30; the unmet items below stay unmet)

- [x] LangGraph StateGraph with PostgresSaver checkpoints (fenced by the job lease, strict deserialization, own `langgraph` schema), conditional and targeted retrieval, bounded retries and budgets (D-028)
- [x] Evidence-completeness check: a log that shows no failure makes Kensa abstain without asking the model; missing failure lines trigger targeted retrieval, at most 2 rounds (D-029)
- [x] Deterministic diagnosis checks beyond quote matching: grounding in the run's own log, category support, conflicting signatures, instruction-like lines rejected; verifier loop with feedback that never quotes evidence (D-029)
- [x] Invalid citations can never be verified: database CHECK constraint plus a persist-time invariant (tested)
- [x] `persist_report` runs **before** the approval interrupt; the report is readable while pending and after rejection (tested in the API, the UI and end to end)
- [x] Idempotent decision and resume: one decision per investigation, a conditional update, and one resume job with an idempotency key; a different decision is a 409 (D-030)
- [x] Remediation planner: fixes plus at most two model edits, each checked against the file, with the diff computed by Kensa; risks and validation steps; Remediation Review UI; decisions recorded only, no repository writes (D-030)
- [x] Tests: malformed output, missing and conflicting evidence, model unavailable (resumes at the diagnosis), prompt injection, verifier-loop and job retry exhaustion, worker killed mid-run and resumed from the checkpoint, a lost lease cannot advance the checkpoint, rejected approval, duplicate approve and resume give exactly one decision and one resumed run, crash between decision and resume
- `ci-local.ps1`: all 11 steps pass after the last change (backend 224, vitest 24, e2e 5 with axe)
- **Dev evaluation** (20 cases, `eval/reports/m3-diagnosis-dev-ollama.md`):
  - **Agent + hybrid:** 20/20 correct, against 17/20 for M2 hybrid. Wrong-but-not-abstaining answers fell from 3 to 0, insufficient-evidence detection rose from 0/2 to 2/2, and there were no regressions.
  - **Agent + full text only:** 16/20, with 1 wrong answer, 5 abstentions and 1 correct answer lost to the grounding rule (c29).
  - **Rules-only:** 15/20, the same as M2.
  - **Held-out test split:** untouched.
- **Not met, and not claimed:**
  - **Generated citation validity:** still about 90% (65/72 for hybrid), not 100%. Every invalid citation is rejected; none is accepted or verified (all 140 accepted citations were re-checked).
  - **Verifier-loop retries:** they ended in abstentions, never in a recovered correct answer, on dev.
  - **Sample size:** the 20 dev cases are synthetic and were also used to check the new rules, so the 20/20 needs confirming on the test split in M5. **M5: not confirmed. The same configuration scored 12/20 on the held-out split (D-039).**

## M4: GitHub integration (public, read-only) `[x]` (approved by the owner 2026-10-30)

- [x] Strict URL parser: repository, Actions, run, attempt and job URLs on github.com only
- [x] Lookup: recent failed runs, failed jobs and their failed steps
- [x] httpx client pinned to api.github.com, GET only; ETag caching; typed handling of 401/403/404/410, rate limits (`X-RateLimit-*`, `Retry-After`), timeouts, oversized responses, expired logs, runs not finished or not failed, private repositories (D-031)
- [x] Secure log-download redirects (D-032):
  - one manual hop to HTTPS on port 443 at an allowlisted log store, with no userinfo or IP literals
  - private-address refusal at connect time
  - a separate credential-free, cookie-free client
  - streamed size and time caps; archives refused; signed URLs never logged, stored or shown
- [x] Redirect test matrix: allowed host OK; disallowed, http, port, userinfo, IP, private resolution, chained and missing-`Location` redirects rejected; no `Authorization` or cookies on the redirected request; no signed query strings in logs or errors; oversized and archive responses refused
- [x] Repository evidence pinned to the run's commit: a snapshot per commit, the workflow and referenced files read at `head_sha`, evidence with the commit and a link to the lines, earlier evidence unchanged by later imports (D-033)
- [x] No live GitHub calls in automated tests (respx refuses unmocked requests). The token is never logged, stored or sent to the UI, and the GitHub CLI token and scoped tokens are refused
- [x] UI: GitHub run lookup and import (a pasted log without a token), GitHub run card, commit links on evidence
- [x] Anonymous live check on real GitHub (`eval/reports/m4-live-github-anonymous.md`): a real run's failed jobs and steps found; the token-required refusal confirmed
- [x] **Live investigation of a genuine failed run** (2026-10-30), in one of the owner's public repositories. Its report holds that repository's real logs, so it is kept out of the public repository.
  - **Token:** fine-grained, Actions read-only, that repository only.
  - **Import:** the log was downloaded via one redirect to `productionresultssa6.blob.core.windows.net`, now confirmed in the allowlist.
  - **Diagnosis:** `db_connectivity` (verified, 4/4 citations).
  - **Citations re-checked:** every citation and evidence excerpt was re-checked against GitHub's own text (`scripts/verify_github_citations.py`), and the repository evidence is pinned to the run's commit.
  - **Fixed during the live runs:** destructive or secret-printing model edits (D-030 amendment) and same-log self-confirmation (D-026 amendment).
  - **Not met:** the stated root cause is probably incomplete. The log shows the database-URL secret was empty, which a human should confirm.
- `ci-local.ps1`: all 11 steps pass (backend 345, vitest 28, e2e 5 with axe)

## M5: Engineering hardening (possible publication checkpoint, requires explicit approval) `[c]` (approved by the owner 2026-10-30 as an engineering and evaluation milestone; the false "verified" diagnoses were to be addressed in M5.1 before M6)

- [x] **Before starting:**
  - the unsafe historical proposals in `6efb4773` and `93616176` withdrawn, with history kept (D-036)
  - the live run's assessment separates what the log shows from the hypothesis, with no access to that repository's configuration
  - the GitHub token unused
- [x] **`SECURITY.md` threat model** (assets, adversaries, entry points, out of scope) plus corpora, built up M1–M5:
  - prompt injection (8/8 caught, 0/8 false positives)
  - secret redaction, including `github_pat_`/`ghp_`/`gho_`
  - SSRF and redirects
  - oversized input
  - diff path traversal
  - per-endpoint workspace authorization
- [x] **Security audit** (`eval/reports/m5-security-audit.md`):
  - fixed: DNS rebinding (Medium) and CSRF on body-less POSTs (Low)
  - stored-data and trace scans: 0 secrets and 0 signed URLs
  - no High or Critical open
- [x] **OpenTelemetry spans** (HTTP, GitHub, graph nodes, embeddings, LLM calls with Ollama's timing breakdown) to a local, git-ignored file. JSON logs carry trace and request IDs.
  - **Not met (found in M5.1):** no database spans. The SQLAlchemy instrumentation declines to run on SQLAlchemy 2.1.6 (D-034 amendment)
- [x] **Held-out evaluation** (protocol pre-registered, D-037; `eval/reports/m5-results.md`): rules only, LLM without retrieval, LLM + full text, LLM + hybrid, agent + full text, agent + hybrid.
  - **Not met (reported as measured):**
    - held-out accuracy is 11–13/20 for every configuration (dev 14–20/20)
    - retrieval and the agent show no measurable held-out gain
    - all 33 wrong answers are grounded in genuine log lines, and "verified" answers were correct 57–78% of the time
  - **Met:** all 400 accepted citations re-checked valid.
  - **Afterwards:** nothing tuned; the v1 test split is spent (D-039)
- [x] **Latency investigated** (D-038 and its amendment): GPU thermal and power throttling (30 W cap) halves generation speed, and the model swap costs ~8 s per hybrid run. No code optimisation was justified, and no system setting was changed
- [x] **Zero serious or critical axe violations** (Playwright, light and dark)
- [~] **`.github/workflows/ci.yml`** mirrors all 11 `ci-local.ps1` checks and is verified by `test_ci_workflow.py` (least privilege, no secrets, mock inference). **Not met:** `check-jsonschema` validation (not installed; needs approval); the workflow has never run on GitHub
- `ci-local.ps1`: all 11 steps pass (backend 398, vitest 29, e2e 5 with axe)

## M5.1: Reliability pass (root-cause trust before M6) `[x]` (implemented and evaluated 2026-10-31. Reviewed by the owner 2026-11-01, who chose M5.2 before M6; accepted with M5.2 on 2026-11-02, which addresses its unmet trust measure)

- [x] **Evidence validity separated from root-cause status** (D-040):
  - The statuses are corroborated / plausible / conflicting / not_established.
  - Genuine citations alone never earn the strongest status.
  - The UI shows the status, a plain explanation and an evidence check instead of the model's confidence.
  - Migration `0007` relabels old reports conservatively.
- [x] **Underlying causes over symptoms** (D-041, D-044):
  - Deterministic cause-level evidence covers missing or empty variables, permissions, databases, Docker, paths, dependencies, memory and assertions.
  - A stated environmental cause outranks the test or build failure that reports it.
  - A corroborated rule-based cause replaces a model answer that established none.
- [x] **Evaluation set v2** (D-042): 60 dev and 60 test cases, including masked, misleading, lookalike and insufficient ones. Written by a separate LLM author, gated, and frozen (`b9ed11aff877d65e`) before any test run. The v1 test set was not used.
- [x] **Benchmark:** dev runs were used to compare changes, and the held-out split was run once per system (`eval/reports/m51-results.md`). The protocol was fixed beforehand (`m51-protocol.md`). One attempt was aborted by Docker Desktop quitting and rerun identically.
  - **Met:**
    - accuracy 41–44/60 (M5: 28–41/60)
    - wrong answers 3 instead of 9–10 in the full-text configurations
    - masked cases better in three of four configurations, and lookalike cases not worse
    - 646/646 accepted citations genuine
    - no latency regression under comparable GPU state
  - **Not met:**
    - wrong strongest-status answers rose from 0–1 (`verified`) to 2–3 (`corroborated`) per configuration
    - `corroborated` was right 88–90% of the time (dev: 100%)
    - all were `test_regression` claims corroborated by an assertion line plus the absence of a recognised cause (D-045)
  - **Afterwards:** nothing tuned, and the v2 test split is spent (D-045). The owner chose the proposed principled change as M5.2 (D-046).
- [x] **Dependency scans** (D-043): `pip-audit` (82 packages) and `npm audit` (303 packages) found nothing; no upgrades. A-6 closed.
- [x] **M0–M5 preserved:** all regression tests pass (see below). No new framework and no architecture rewrite.
- `ci-local.ps1`: all 11 steps pass (backend 448, 0 skipped; vitest 29; e2e 5 with axe)

## M5.2: A test regression is never corroborated `[x]` (implemented and checked 2026-11-02; approved by the owner 2026-11-02, who chose M6 without a v3 set)

- [x] **The rule** (D-046), chosen by the owner after M5.1's held-out result:
  - A failing assertion is a symptom, so a `test_regression` claim is at most `plausible`.
  - The deterministic fallback can therefore no longer report one.
  - Two new tests fail on the M5.1 verifier and pass on M5.2.
  - No pattern, prompt, model or other category changed, and the two wordings M5.1 missed on test were not added.
- [x] **v2 dev regression check** (`eval/reports/m52-results.md`), one run of the four configurations:
  - No wrong answer is `corroborated`, and `corroborated` is right every time (33/33, 27/27, 28/28, 24/24).
  - **Correct:** 55/52/53/53 (M5.1: 55/54/54/53). One loss is D-046's (d58, LLM + full text) and two are model run-to-run variation.
  - **Latency:** no change attributable to D-046.
- [x] **Spent v2 test split, derived exactly from M5.1's stored run (not a held-out result):** wrong `corroborated` answers fall from 2–3 to 0 per configuration, by construction. Correct answers go from 41/44/44/44 to 41/43/44/44 (t58 lost).
- **Not measured:** the effect on new failures, which would need a new independent set (v3). The owner chose to go to M6 without one; M6's README and demo state the limitation.
- `ci-local.ps1`: all 11 steps pass at `5f001dc` and again after the results and documentation (backend 450, 0 skipped; vitest 29; e2e 5 with axe)

## M6: Recruiter-ready release (publication is a separate approval) `[x]` (prepared locally 2026-11-02, with the owner's 10 additional requirements; approved by the owner 2026-11-03)

- [x] **Replay demo** (D-048):
  - **The build:** a static build of the real UI (`npm run build:replay`) answering from 6 real runs recorded in the production settings: the 3 samples, plus 3 v2 dev cases with their repositories.
  - **Labelling:** every page carries a banner with the recording date, model and GPU, plus a Replay badge.
  - **Behaviour:** decisions are kept in the tab only, and creating investigations is disabled.
  - **Verified:**
    - `test_replay_recording.py` checks every recorded line and all 20 citations against the source files; `record_replays.py --verify` matches the stored runs.
    - The e2e tests prove the replay build makes no request outside its own files, and that it works with every other request blocked.
    - It also passes with Docker, Ollama and the backend stopped.
  - **Approvals:** labelled temporary before and after the decision.
- [x] **en/ja UI toggle** (D-047):
  - No new dependency. `ja.ts` is checked against the English keys at build time, and its placeholders and translation coverage by tests.
  - Drafted from a fixed glossary; every string reviewed, and six changed.
  - axe passes (0 serious or critical) in both languages and themes, for the live app and the replay.
  - Keyboard-only use, dates per language, and phone width (375 px, no sideways scrolling) are tested. The phone check found the header overflowing; fixed.
- [x] **Documentation:**
  - README rewritten for a five-minute reader, with a Mermaid diagram, honest results and a 日本語概要
  - `docs/evaluation.md` (methodology and every measurement) and `docs/testing.md`
  - ARCHITECTURE diagrams checked against the code; the deterministic fallback and the replay build added
  - SECURITY.md corrected: archives are refused, never unpacked
- [x] **Screenshots and demo video:**
  - `npm run media` captures 10 screenshots (one at phone width) and a 75 s video from the replay build.
  - The video has English captions in the picture, English and Japanese caption files, and a transcript, all generated from the recording's own facts.
  - The images exposed 2 display defects, fixed with tests. A frame of every caption was checked against its words.
- [x] **Licence and privacy** (D-049):
  - MIT `LICENSE`.
  - `THIRD_PARTY_NOTICES.md` generated from local metadata: 70 Python packages, 8 bundled frontend packages, 2 models. The model and service licences were checked upstream (D-049 amendment).
  - **Privacy audit:**
    - covered the tree, the recording, the media metadata and the full git history
    - the local path removed from tracked files
    - the history still holds it in three commits, which needs the owner's decision
- [x] **Evaluation documentation reconciled** with the M5–M5.2 reports. It shows each split's status, and keeps measured, derived and not-measured results apart.
- [x] **A fresh clone shows a complete investigation in under 5 minutes of setup:**
  - **Result:** 88 s from `git clone` of `82ab3c3` to a finished sample investigation on screen, following the README with Rules only and Ollama stopped (first run, `ee634ad`: 54 s). Caches were warm; first-time downloads come on top.
  - **What the check found:** the sample logs had never been in git (`.gitignore` `*.log`), which gave HTTP 500 on any fresh clone. Fixed, with a guard test.
- `ci-local.ps1`: all 11 steps pass (backend 464, 0 skipped; vitest 44; e2e 17 with axe in en and ja)

## Publication preparation (the owner's decisions of 2026-11-03) `[x]`

- [x] **A clean publication snapshot** with a new, single-commit git history. The development history stays private and unchanged (D-050).
- [x] **Only intentionally public files:** 1,167 files. Left out: the private working notes, development-tool configuration, the live-run reports and the snapshot script.
- [x] **GitHub Actions** pinned to full-length commit SHAs, each verified against its release tag:
  - `contents: read` for CI
  - a manual-only Pages workflow, whose deploy job alone can write
- [x] **Dependency audits:**
  - `pip-audit`: no known vulnerabilities in the 82 locked Python packages
  - `npm audit`: none in the packages the app ships; one dev-only advisory (`minimatch`, through the lint tools) with no non-breaking fix
- [x] **Third-party notices** shipped with the static replay build and linked from every page.
- [x] **Checked on the snapshot itself:**
  - privacy scan: clean
  - fresh clone: 38 s to a finished investigation
  - full local CI: 11/11 (backend 467, vitest 44, e2e 17)
  - offline replay: 10/10, with Docker, Ollama and the backend stopped

## v1.0 public release (approved by the owner 2026-11-08) `[x]`

- [x] Approved for release as v1.0: a public repository, the replay demo on GitHub Pages, and the `v1.0.0` release.
- [x] Development-tool names removed from the public files; the two frozen dataset notes keep their wording (D-050 amendment).
- [x] The demo's banner says it is a prerecorded interactive replay, not live AI inference.
- [x] The README links the live demo, the source, the video and the docs.
- [x] The replay e2e tests can also check a deployed copy of the demo (`KENSA_REPLAY_URL`).

## Optional future work (not before M6)

Approved PR creation, MCP connectors, DSPy, more providers, multi-repo investigations, incident clustering, trends.
