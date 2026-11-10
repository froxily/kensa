# Decisions

A lightweight decision record. Newest entries go at the bottom. Each entry gives the decision, why it was made, and its consequences. **Status** is one of: accepted, provisional (pending measurement), or superseded.

---

### D-001: Modular monolith backend
- **Status:** accepted (2026-10-29)
- **Decision:** a single FastAPI process with cohesive modules (api, ingestion, retrieval, inference, agents, jobs, github, evaluation). No microservices.
- **Why:** one developer and one laptop. Module boundaries give the separation without the cost of network calls or extra deployment.

### D-002: PostgreSQL + pgvector as the only datastore
- **Status:** accepted
- **Decision:** a single PostgreSQL 18 instance (`pgvector/pgvector:0.8.7-pg18`) holds application data, FTS, vectors, LangGraph checkpoints, and the job queue.
- **Why:** fewer moving parts and transactional consistency between evidence, reports, and jobs. Hybrid search uses SQL alone.

### D-003: Ollama runs natively on Windows, loopback only
- **Status:** accepted
- **Decision:** Ollama is not containerised. Only Postgres runs in Docker, and the backend runs natively in development.
- **Why:** direct GPU access with no Docker GPU passthrough, and Ollama never needs `OLLAMA_HOST=0.0.0.0`.

### D-004: Python 3.13 managed by uv
- **Status:** accepted
- **Decision:** the project pins Python 3.13. The system has Python 3.14 and an msys64 Python on PATH, and uv's managed interpreter avoids both.
- **Why:** LangGraph's classifiers currently stop at 3.13.

### D-005: psycopg 3 as the single PostgreSQL driver
- **Status:** accepted
- **Decision:** SQLAlchemy uses `postgresql+psycopg://`. `langgraph-checkpoint-postgres` (M3) uses psycopg 3 too.
- **Why:** one driver and one set of connection semantics.

### D-006: Postgres-backed leased job queue (no Redis/Celery)
- **Status:** accepted (design; implemented in M1)
- **Decision:** a `jobs` table claimed with `FOR UPDATE SKIP LOCKED`. It provides leases with heartbeat, expired-lease reclaim, bounded retries with backoff and jitter, unique idempotency keys, one active job per investigation, and fencing on writes.
- **Why:** durable crash recovery and duplicate protection with no extra infrastructure. The owner explicitly asked for leases, crash recovery, bounded retries, and duplicate protection.

### D-007: Deterministic-first diagnosis
- **Status:** accepted
- **Decision:** an error-signature extractor and a rule classifier (8 categories) run before any LLM call. They serve as an LLM input feature, the mock provider's basis, and the evaluation baseline.
- **Why:** cheap and explainable. It also gives an honest baseline the LLM has to beat.

### D-008: Persist the report before the approval interrupt
- **Status:** accepted (design; implemented in M3)
- **Decision:** `persist_report` runs before the LangGraph `interrupt()`. Approving or rejecting changes only the proposal status. The approval node has no side effects before `interrupt()`. Decisions are conditional updates, and resumes are idempotent per decision.
- **Why:** users must be able to see results whatever the approval state, and LangGraph re-runs the interrupted node on resume.

### D-009: Primary local model and inference options
- **Status:** accepted (2026-10-30, from measurements)
- **Decision:**
  - Model: `qwen3:4b-instruct-2507-q4_K_M` (digest `0edcdef34593`).
  - Every request sends `num_gpu=99` (all layers on the GPU) and `num_ctx=8192`.
  - Fall back to 6144 if other GPU workloads reduce headroom. Never use 12288 or above on this card.
  - These are per-request options (D-012), so there are no `OLLAMA_*` env vars and no system-wide change. No alternative model is needed.
- **Evidence:** `eval/reports/m0-model-benchmark.md` (Ollama defaults) and `eval/reports/m0-model-benchmark-numgpu99.md` (all layers on GPU). The second run reproduced the peaks of an earlier identical run exactly. Ollama 0.40.13, RTX 3050 Laptop with 3962 MiB usable VRAM.

  | Config | Ollama allocation | Peak VRAM | tok/s (median) | Warm latency |
  |---|---|---|---|---|
  | Defaults @4096 | 3371 MiB, only 2236 in VRAM (partial offload) | 2337 MiB | 21.3 | ~3.9 s |
  | `num_gpu=99` @4096 | 3032 MiB, all in VRAM | 3125 MiB | 51.6 | 1.9 s |
  | `num_gpu=99` @8192 | 3612 MiB, all in VRAM | 3705 MiB | 49.4 | 2.0 s |
  | `num_gpu=99` @12288 | 4192 MiB, which exceeds the 3962 usable, so it spills into shared memory | 3901 MiB | 42.5 | 3.6 s |

- **Why:** Ollama's automatic placement is conservative on this machine: it kept about a third of the model on the CPU and ran 2.4× slower. With every layer requested on the GPU, 8192 context fits with about 257 MiB headroom.
- **Caveats:**
  - Measured with prompts of at most 1.3k tokens. The KV cache is pre-allocated, but the M1 live run must re-check peak VRAM with long evidence prompts.
  - Schema validity was 5/5 at every size.
  - Category match was 2/5 on synthetic logs with a prompt that did not define the categories. That is not an accuracy signal, but it supports D-007 (deterministic-first).

### D-010: Repository stays local and private
- **Status:** accepted
- **Decision:** no remote, no push, and no GitHub repo until the owner explicitly approves. CI is written and validated locally (`ci-local.ps1`, `check-jsonschema`). M5 is only a possible publication checkpoint.

### D-011: Single local operator with workspace-scoped authorization
- **Status:** accepted
- **Decision:** no login through M4. Every row carries `workspace_id`, and every query goes through a server-side authorization dependency. Demo Mode is read-only.
- **Why:** keeps MVP scope honest while making real auth a contained later change.

### D-012: No system-wide configuration changes by default
- **Status:** accepted
- **Decision:** repo-local git identity and `.gitattributes` instead of global git config; a per-container memory limit instead of `.wslconfig`; per-request Ollama options instead of `OLLAMA_*` user env vars. A system-wide change happens only on measured need, after explaining its effect and getting approval.

### D-013: Development workflow (internal)
- **Status:** accepted. A note on how the development work was organised; it is not part of this public record.

### D-014: Planned designs
- **Status:** accepted as design, to be detailed when built
- **Retrieval fusion (M2):** Reciprocal Rank Fusion (k = 60) over signature, FTS, and vector channels, with per-channel weights tuned on the dev split only.
- **GitHub log redirects (M4):** automatic redirects disabled; one manual hop to allowlisted HTTPS log-storage hosts; private-address rejection at connect time; a separate credential-free client; size/time caps; safe in-memory zip handling; signed URLs never logged, stored, or traced. The host allowlist will be pinned from real responses and recorded here.

### D-015: Synchronous database access (psycopg 3 sync)
- **Status:** accepted (2026-10-29)
- **Decision:** SQLAlchemy uses synchronous sessions and engines. DB-touching endpoints are plain `def` handlers, which FastAPI runs in its threadpool. The M1 worker runs DB calls in threads.
- **Why:** psycopg's async mode does not work on Windows' default `ProactorEventLoop`, and this project is developed on Windows. Sync access avoids loop-policy hacks and behaves the same on Linux CI.
- **Consequence:** M3 should use the sync `PostgresSaver` inside the worker thread. Revisit only if measurements show DB I/O concurrency is a bottleneck.

### D-017: M1 calls Ollama directly over httpx; LangChain/LangGraph arrive in M3
- **Status:** accepted (2026-10-30)
- **Decision:** `OllamaProvider` posts to `/api/chat` with `httpx`: JSON-schema `format`, the D-009 options, one repair retry, and typed errors. LangChain (`langchain-ollama`) and LangGraph are added in M3, where graph orchestration, checkpoints and interrupts need them.
- **Why:**
  - M1 needs exact control of per-request options (`num_gpu`, `num_ctx`, `keep_alive`).
  - The tests mock the HTTP API directly.
  - It adds no new dependencies.
- **Consequence:** the `InferenceProvider` seam isolates the change, so switching the provider's internals in M3 does not touch the pipeline.

### D-018: Verification statuses and confidence caps
- **Status:** accepted (2026-10-30)
- **Decision:** the deterministic verifier assigns one of:
  - **verified:** all citations check out and the category agrees with the signature rules
  - **supported:** at least one citation checks out, but not everything is corroborated
  - **contradicted:** citations check out, but strong rules disagree
  - **unknown:** nothing is verified, or the model declined

  The model's self-reported confidence is capped at 1.0 / 0.7 / 0.4 / 0.2 for those statuses respectively. With status `unknown`, the UI does not present the model's explanation as a cause. A quote found on another line of the same evidence block is accepted with the line corrected, and the correction is noted. Risky fixes are flagged, not removed.
- **Why:** never present an unverified claim with the model's own (over)confidence. In the M1 live check, the model reported 0.98–1.0 on every case.
- **Amendment (M2, 2026-10-30, commit 7fb7362):** quotes from Markdown sources (knowledge notes, repository docs, incidents) are compared without inline markup (backticks, asterisks); logs and code are still compared as written. The first dev diagnosis run showed the model quoting note prose without its markup.

### D-019: Worker runs as a thread inside the API process
- **Status:** accepted (2026-10-30)
- **Decision:** the leased worker (D-006) is started in the FastAPI lifespan (`KENSA_WORKER_ENABLED`). It processes one job at a time, so LLM concurrency is 1. Tests disable it and drive `Worker.run_once()` directly.
- **Why:** one process to run locally, nothing new to install. The queue is in PostgreSQL, so a separate worker process can be added later without changing the protocol.

### D-020: End-to-end tests use an isolated backend and database
- **Status:** accepted (2026-10-30)
- **Decision:**
  - Playwright starts `scripts/e2e_server.py`: port 8010, its own `kensa_e2e` database (migrated and emptied per run), the rules-only provider.
  - It also starts a Vite dev server on port 5174, proxied to that backend.
  - axe runs the WCAG 2.1 A/AA rules on the main pages in light and dark themes and fails on any serious or critical violation (stricter than the "no critical" roadmap item).
- **Why:** deterministic, model-free end-to-end tests that never touch development data.

### D-021: The prompt states each output field's purpose and length target
- **Status:** accepted (2026-10-30)
- **Decision:** the system prompt lists every output field with its purpose and target length, and asks for citation phrases of at least 10 characters.
- **Why:** Ollama compiles the JSON schema into a decoding grammar. `maxLength` therefore truncates text, and the model never sees the schema's field descriptions.
- **Evidence:** in the first live run, summaries were cut off mid-sentence at 600 characters. One later citation was a bare `^`, which the verifier correctly rejected. After the change, all four live cases were verified with 4/4 citations and one-sentence summaries (`eval/reports/m1-live-check.md`).

### D-016: TypeScript pinned to 6.0.x in the frontend
- **Status:** accepted (2026-10-29)
- **Decision:** `typescript ~6.0.3` in `frontend/package.json`. The globally installed TypeScript 7 is not used by the project.
- **Why:** `typescript-eslint` 8.72 (the latest) declares `typescript >=4.8.4 <6.1.0`. Revisit when it supports TypeScript 7.

### D-022: Document scopes and identities (M2)
- **Status:** accepted (2026-10-30)
- **Decision:** documents are identified per scope by partial unique indexes:
  - an investigation's log by its content hash
  - a repository file by its path
  - workspace knowledge (kb notes and incidents) by its name

  Re-indexing is incremental: an unchanged hash is skipped, a changed file is re-chunked in place, and a vanished file is removed. Retrieval scope is the investigation's logs + its repository's files + workspace kb + other incidents.
- **Why:** identical content in different files (empty `__init__.py`, shared configs) must not collide, and re-indexing must not duplicate.

### D-023: Fusion weights fixed before evaluation, not tuned
- **Status:** accepted (2026-10-30)
- **Decision:** RRF k = 60 with weights signature 1.0 / fts 0.8 / vector 0.8 / tail 0.5. These were set before the first evaluation and have not been changed since.
- **Why:** with a 20-case dev split, tuning would overfit, and the numbers were meant to show the design as built.
- **Measured result (dev, `eval/reports/m2-retrieval-dev-ollama.md`):** hybrid is roughly level with M1. FTS alone scored highest. Re-weighting is a candidate for later work, to be validated on dev and confirmed once on test in M5.

### D-024: Embeddings run on the GPU, sequentially with the LLM
- **Status:** accepted (2026-10-30, from `eval/reports/m2-embedding-placement.md`)
- **Decision:** `qwen3-embedding:0.6b` uses Ollama's default placement (`embedding_num_gpu=None`). The embedding and LLM models swap on the GPU and are never used concurrently: the pipeline embeds first, then diagnoses.
- **Why:**
  - On the CPU the embedder managed 0.8 chunks/s, versus 41.3 on the GPU.
  - Both models together (3.6 + 1.2 GB) cannot fit in 3.96 GB usable VRAM, so loading the embedder evicts the LLM.
  - A model reload costs seconds, whereas CPU embedding of a repository costs minutes. This also matches the owner's "run sequentially" instruction.

### D-025: Evaluation dataset authorship, gates and freeze
- **Status:** accepted (2026-10-30)
- **Decision:**
  - The dataset is written by a separate LLM author, isolated from Kensa's code. Kensa's development supplied only the spec and the gates.
  - Quality gates run in `scripts/freeze_dataset.py`. The anti-template check uses an explicit runner/docker boilerplate allowlist, never frequency filtering.
  - A line-ending-independent SHA-256 manifest freezes the dataset, and evaluation refuses to run on a changed dataset.
  - The test split is locked for M5.
- **Why:** the system's author should not write its exam. Details are in `eval/datasets/v1/AUTHORING.md`.

### D-026: Incidents are never their own evidence; evaluation disables incident indexing
- **Status:** accepted (2026-10-30)
- **Decision:**
  - Verified investigations are indexed as `incident/<id>` documents, and retrieval excludes the investigation's own incident.
  - `scripts/evaluate.py` sets `index_incidents=False`.
- **Why:** prevents self-confirmation, and leakage between evaluation cases.
### D-027: M2 conditional approval; full-text search stays the retrieval baseline
- **Status:** accepted (2026-10-30, owner)
- **Decision:**
  - M2 is approved on condition that its two unmet acceptance items stay documented as unmet: hybrid retrieval did not beat full-text search on dev, and 88–93% (not 100%) of generated citations were valid.
  - Full-text-only retrieval is kept as a selectable configuration and as the baseline in every evaluation. Hybrid weights get no extensive tuning; any tuning uses dev cases only, and the test split stays untouched until M5.
- **Why:** the measurements did not show a hybrid gain, so the simpler channel remains the reference point.

### D-028: Agent workflow on LangGraph with fenced PostgreSQL checkpoints (M3)
- **Status:** accepted (2026-10-30)
- **Decision:**
  - The investigation runs as a LangGraph `StateGraph` (`agents/graph.py`) over the M1/M2 node functions. `run_investigation` stays as the linear runner for the M2 evaluation baselines.
  - Checkpoints use the sync `PostgresSaver` with `durability="sync"`, in their own `langgraph` schema. Alembic migration 0004 creates the tables as a frozen copy of the library's migrations; the app never calls `setup()`. A test compares the copy with the installed library.
  - A `PostgresSaver` subclass re-checks the job lease before every checkpoint write.
  - The graph state holds only JSON-like values, and deserialization uses LangGraph's strict allowlist (`allowed_msgpack_modules=None`).
  - LangSmith tracing variables are forced to `false` in the worker process.
  - Budgets per run: 3 diagnosis attempts, 2 targeted retrieval rounds, 4 model calls, 900 s.
- **Why:**
  - **Durable resume:** a worker crash costs one step, not the whole run.
  - **Schema control:** the schema stays under Alembic.
  - **Fencing:** keeps D-006's guarantee for checkpoints.
  - **Strict state:** removes the deserialization risk the library warns about.
- **Packages:** `langgraph` 1.2.18 and `langgraph-checkpoint-postgres` 3.2.0, as named in the M3 roadmap the owner approved. They pull in `langchain-core` and `langsmith`, which stays disabled.

### D-029: Deterministic completeness gate and claim checks; abstention over guessing (M3)
- **Status:** accepted (2026-10-30)
- **Decision:**
  - **Completeness gate:** a log with no failure vocabulary at all makes Kensa abstain without a model call. Missing failure lines trigger targeted retrieval.
  - **Claim checks:** the verifier also requires:
    - a verified citation from the run's own log
    - a cited line that shows the claimed category (signature rules or indicator vocabulary)
    - no strong signature of another category on a cited log line unless the claimed one also has one
  - **Instruction-like lines:** never accepted as citations.
  - **Rejection and retries:** a failed check gives "cause not established". Where a retry could help, the model is asked again with feedback that never quotes evidence.
- **Why:**
  - In M2 every wrong LLM answer was a "supported" `test_regression` whose citations did not show a test failure, and the model almost never abstained.
  - Before the change, an offline replay on the stored M2 dev diagnoses broke no correct answer and turned 3 wrong answers into "not established".
- **Limits:**
  - The vocabularies were written from the category definitions and checked on dev only (never on test).
  - They catch claims that their citations do not support, not a wrong claim that cites a genuinely matching line (dev case c16).

### D-030: Read-only remediation proposals with human approval (M3)
- **Status:** accepted (2026-10-30)
- **Decision:**
  - **Proposals:** created only for verified or supported diagnoses. They come from the diagnosis's fixes, plus at most two model edits.
  - **Edit validation:** an edit is accepted only if its `find` text occurs exactly once in the full repository file, contains no secret or instruction-like text, and its path is safe. Kensa computes the unified diff with `difflib`.
  - **Order:** the report and proposals are persisted before the approval interrupt.
  - **Decisions:** recorded by the API in one transaction with the resume job. There is one decision per investigation, and repeating it returns the stored one. A different decision is a 409.
  - **Nothing is applied:** approval changes only the proposals' status.
  - **Rules-only runs** produce "template" proposals without diffs.
- **Why:** a model never writes a diff that a human might apply blindly. Every change shown is checked against the file, and the decision is auditable and exactly-once.

### D-031: Read-only GitHub access: anonymous by default, an optional read-only token for job logs (M4)
- **Status:** accepted (2026-10-30, owner chose the token option)
- **Finding:** GitHub answers anonymous job-log downloads with `403 "Must have admin rights to Repository."`, even for public repositories (probed 2026-10-30). Anonymous check-run annotations only say "Process completed with exit code 1." Run, job, step and repository-file data are public.
- **Decision:**
  - **Hosts:** only `https://api.github.com` is ever contacted, with GET only. API paths are built from strictly validated parts; the URL parser accepts only `https://github.com/<owner>/<repo>` pages for a repository, its Actions tab, a run, a run attempt or a job.
  - **Token:** optional, `KENSA_GITHUB_TOKEN`. The owner creates it as fine-grained, limited to public repositories, read-only, with no permissions.
    - It is a `SecretStr`, never logged, stored, returned or forwarded on a redirect. A blank value means anonymous access.
    - OAuth, app and refresh tokens are refused (`gho_`, `ghu_`, `ghs_`, `ghr_`; the GitHub CLI login is `gho_`).
    - A token whose responses carry OAuth scopes is refused at first use.
  - **Without a token:** run, job and step lookup and file fetching work, and the user pastes the job log.
  - **Network hygiene:** clients use `trust_env=False` (no proxy variables, no `.netrc`). An in-process ETag cache serves repeat lookups with `304`, sparing the anonymous budget of 60 requests per hour.
  - **Errors** are typed and shown with a clear message: 404, 410, 403, 401, rate limits (`X-RateLimit-*`, `Retry-After`), timeouts, oversized responses, expired logs, runs still in progress or not failed, private repositories.
  - **Import is synchronous** in `POST /api/investigations`. The network part runs before the database transaction, so a failed import stores nothing.

### D-032: Log-download redirects: one validated hop, public addresses only (M4)
- **Status:** accepted (2026-10-30)
- **Decision:**
  - **One hop:** the job-log endpoint's `302` is followed manually, exactly once. The `Location` must be `https` on port 443, with no userinfo and no IP literal.
  - **Allowlist:** the host must match a tight allowlist, `productionresultssa<N>.blob.core.windows.net` plus two `*.actions.githubusercontent.com` names. A broad `*.blob.core.windows.net` would admit storage anyone can create.
  - **Confirmed 2026-10-30:** the first authenticated download (a job in one of the owner's public repositories) redirected once to `productionresultssa6.blob.core.windows.net`, which the allowlist pattern matches. An unknown host would fail closed (`redirect_refused`).
  - **Fresh client:** the hop uses a new client with no `Authorization`, no cookies and no further redirects (a second redirect is refused).
  - **Address check:** every connection goes through `PublicAddressBackend`. It resolves once, refuses any non-global address (private, loopback, link-local, shared, reserved, multicast, IPv4-mapped), connects to the vetted address, and still verifies TLS against the hostname. This defeats DNS rebinding.
  - **Caps:** downloads stream under a size cap (16 MB) and a deadline. Archives are refused by content type and by the `PK` signature, because Kensa downloads only per-job plain-text logs, never run-level zip archives.
  - **Signed URLs** are never logged, stored or shown; `safe_url` drops the query string.
  - Over-long logs keep their last 2 MB (where the failure is), with a first line saying what was dropped.

### D-033: Repository evidence is pinned to the run's commit (M4)
- **Status:** accepted (2026-10-30)
- **Decision:**
  - **Snapshots:** a GitHub repository is stored once per commit, with `repositories.commit_sha` set. The unique key covers (workspace, provider, name, commit), and a CHECK requires a commit for GitHub.
  - **Pinned reads:** the workflow file and up to 6 source files that the log mentions near failure lines are read at the run's `head_sha` into that snapshot.
  - **Path filtering:** paths are mapped out of the runner workspace. System, dependency and parent-directory paths are refused.
  - **Retrieval** for the investigation is scoped to that snapshot, and the evidence API returns `commit_sha` plus a GitHub link to the cited lines at that commit.
  - **Run record:** `workflow_runs` records the run, attempt, job, failed steps, log source, and fetched and missing files.
- **Why:** re-importing the same repository at another commit must never change an earlier investigation's evidence (tested).

### Amendments after the M4 live investigation (2026-10-30)
- **D-031, cause of the 403:**
  - GitHub refuses anonymous job-log downloads with `403 "Must have admin rights to Repository."`. This was confirmed on `pytest-dev/pytest` and on one of the owner's public repositories.
  - The response had no `Location` header, and rate limits were not exhausted (41 and 51 of 60 remaining).
  - GitHub documents that a signed-in user is needed for workflow-run information, "including for public repositories". The endpoint needs the fine-grained **Actions: read** repository permission.
  - The owner's token is fine-grained, limited to that one repository, with **Actions: Read-only** (and Metadata: Read-only, which GitHub requires) and a short expiry. GitHub reported no OAuth scopes.
- **D-030, structural checks on model edits:** the live runs produced two unsafe edits that passed the textual checks. One deleted a step's `env` and `run` keys and cut `working-directory: ingest` to `ing`. The other printed a secret-backed variable and left `if [[ \` dangling.
  - An edit is now also dropped when:
    - it reaches the schema's length cap (`truncated`)
    - the file no longer parses as YAML, JSON, TOML or Python (`breaks_syntax`); files are parsed only, never executed
    - a YAML key that existed disappears (`removes_existing_keys`)
    - a workflow step loses `run`/`uses` (`breaks_workflow`)
    - a changed `run:` script's shell constructs no longer balance (`breaks_shell`)
    - an added line prints a variable that holds a secret (`exposes_secret`)
  - The planner prompt now states the length limit and "only add or change values".
- **D-026, same-log incidents:** re-investigating the identical job log retrieved the earlier investigation's incident, so its conclusion became evidence for itself. Retrieval now excludes the incident of every investigation whose log has the same content hash, the own investigation included (tested).

### D-034: Local observability: OpenTelemetry to a JSONL file, logs joined by trace and request ids (M5)
- **Status:** accepted (2026-10-30)
- **Decision:**
  - **Packages:** the OpenTelemetry SDK, with the FastAPI and SQLAlchemy instrumentations (`opentelemetry-sdk` 1.45.1, instrumentations 0.66b1).
  - **Export:** spans go to `.telemetry/**/traces.jsonl` (git-ignored, rotated at 20 MB). No network exporter is configured, and a test fails if `otlp` appears in the source.
  - **Spans:** HTTP requests (health and the live stream excluded), SQL statements (no parameter values), jobs, the investigation run, every graph node, model calls, embeddings and GitHub requests.
    - Model-call spans carry Ollama's own load, prompt-evaluation and generation timings, token counts and tokens/s.
    - GitHub and Ollama calls are traced by hand: the httpx auto-instrumentation would record full URLs, including signed log URLs.
  - **Logs:** every JSON log line carries `trace_id`/`span_id` and the HTTP `request_id` (`X-Request-ID`, echoed or generated).
  - **Tests and switch:** tests turn tracing off by default. `KENSA_TELEMETRY_ENABLED=false` turns it off anywhere.
- **Why:** to measure where time goes (the M3 latency question) and to join logs to traces, at ₹0 and with nothing leaving the machine.
- **Amendment (2026-11-01, found in M5.1's final CI):** SQL spans were never produced.
  - `opentelemetry-instrumentation-sqlalchemy` 0.66b1 supports SQLAlchemy < 2.1, and the lock has had 2.1.6 since before M5. On startup it logs that it will not instrument.
  - No test checked for SQL spans, and the M5 report's "database" spans claim was not verified.
  - The other spans are unaffected.
  - **Not fixed in M5.1:** that needs either a compatible instrumentation release or forcing it past its version check, untested. Both are dependency or observability changes for the owner to approve.

### D-035: Security hardening from the M5 audit: trusted hosts and JSON-only state changes
- **Status:** accepted (2026-10-30)
- **Decision:**
  - **Trusted hosts:** `TrustedHostMiddleware` answers only `Host: 127.0.0.1` or `localhost` (`KENSA_ALLOWED_HOSTS`). This defeats DNS rebinding, where a web page re-points its own domain at 127.0.0.1.
  - **JSON-only state changes:** every POST/PUT/PATCH/DELETE must be `Content-Type: application/json` (415 otherwise). Cross-site pages can then only send such requests after a CORS preflight, which fails for any origin but the UI. This closes CSRF, including the body-less `/retry`.
- **Why:** the audit found that the API answered any `Host` header, and that body-less POSTs were reachable by simple cross-site requests.

### D-036: Unsafe historical proposals are withdrawn, never deleted (M5)
- **Status:** accepted (2026-10-30, owner request)
- **Decision:**
  - **Status:** proposals gain the status `withdrawn`, with `withdrawn_reason` and `withdrawn_at` (a CHECK ties the reason to the status).
  - **Audit trail:** the proposal, its diff and its text stay unchanged, and a timeline entry records each withdrawal.
  - **Effect:** withdrawn proposals are never approved. If nothing actionable remains, the investigation is closed without a decision.
  - **Re-checking:** `scripts/withdraw_unsafe_proposals.py` re-checks every stored diff with today's edit checks, rebuilding the edited file from the stored diff. Only investigations named by the owner are withdrawn.
- **Applied 2026-10-30:** investigations `6efb4773…` (diff: `removes_existing_keys`) and `93616176…` (diff: `exposes_secret`), with their text proposals marked non-actionable. The re-check found no other unsafe stored diff.

### D-037: M5 held-out evaluation protocol (pre-registered)
- **Status:** accepted (2026-10-30)
- **Decision:**
  - **Pre-registration:** `eval/reports/m5-protocol.md` fixes the six configurations, the metric definitions ("grounded but wrong", "false confidence", correct and missed abstentions) and the stated limits before the test split is run for the first time.
  - **Freeze:** the system is frozen at a commit before the run, and the dev split is run under the same commit for comparison.
  - **No tuning:** test results are not used to tune anything. Further optimisation requires a new, independently written evaluation set.

### D-038: Inference latency: measured, no code regression, no optimisation (M5)
- **Status:** accepted (2026-10-30)
- **Measurement:** `eval/reports/m5-latency-dev.md` and `.telemetry/m5-latency-dev/traces.jsonl`, 8 dev cases. Both runs use the same model, options and code paths.

  | | diagnosis call p50 | model load p50 | prompt evaluation p50 | generation p50 | output tokens p50 | tokens/s |
  |---|---|---|---|---|---|---|
  | M2 pipeline | 16.2 s | — | — | — | — | — |
  | M3 agent | 15.8 s | 6.7 s | 1.0 s | 8.0 s | 378 | 47 |

  The model reloaded on every diagnosis call (16 of 16) after the embedder ran. Generation ran at 47 tokens/s with the JSON schema enforced, against 90–100 in an unconstrained probe.
- **Finding:** the ~29 s per call seen in the M3 evaluation did not reproduce. The M3 agent is not slower than the M2 pipeline, so there is no code regression. The earlier figure was environmental, and its cause is unknown (thermal or power state during the 35-minute run is a candidate, not a measurement).
- **Decision:** no optimisation.
  - About 40% of a diagnosis is reloading the LLM after the embedder; the two models cannot share 4 GB.
  - Avoiding the reload would need CPU embeddings (measured at 0.8 chunks/s in D-024, which is slower overall) or system-wide Ollama settings (not approved).
  - Shorter outputs would trade answer quality for speed without a measured need.
  - The long held-out run is checked for latency drift over time.
- **Amendment (M5 held-out run, 2026-10-30):** the drift check found the cause of the variation. During the dev run the GPU reached its 87 °C target and the driver held its power limit at 30 W (default 60 W), with "SW Thermal Slowdown" and "SW Power Cap" active. The median busy clock was 480 MHz and generation ran at 22 tokens/s. In the held-out run the limit was back at 60–95 W, the median busy clock was 1,237 MHz and generation ran at 42 tokens/s, with the same commit and output length (`eval/reports/m5-results.md`, `m5-gpu-throttle.csv`). The decision stands: the cost is environmental, plus the model swap (an embedding-model load in 59 of 103 embedding calls, an LLM reload in 60 of 108 diagnosis calls), which has no faster measured alternative on 4 GB. No system or power setting was changed.

### D-039: After the held-out result: report, do not tune; the v1 test split is spent (M5)
- **Status:** accepted (2026-10-30)
- **Result:** on the held-out split every configuration scored 11–13/20 (dev: 14–20/20). Retrieval and the agent showed no measurable gain; 33 of 33 wrong answers cite genuine lines from their own log; "verified" answers were correct 57–78% of the time for the LLM configurations (`eval/reports/m5-results.md`).
- **Decision:**
  - **No change:** nothing in Kensa (prompts, rules, retrieval defaults, verifier, thresholds) is changed in response to the test answers. The production configuration stays agent + hybrid, although full text matched it on held-out at half the latency: switching on that evidence would be tuning on the test split.
  - **The v1 test split is spent:** any future result on it is not a held-out result and must be labelled as such.
  - **Further work needs evaluation set v2:** independently written, larger (≥ 60 per split), with its own frozen dev/test split. Its first questions: rule-hint anchoring, causes that surface through test runners and Docker builds, a stricter meaning of "verified", and full text versus hybrid.
- **Why:** reporting the drop honestly, and keeping the next round's held-out set clean, is worth more than a better number on a set that is no longer independent.


### D-040: Root-cause status is separate from evidence validity; nothing is "verified" (M5.1)
- **Status:** accepted (2026-10-30, owner instruction after M5)
- **Problem:**
  - M5's "verified" meant: every citation is genuine, the claim is grounded in the log, and the model agrees with the signature rules.
  - On the held-out split, 22–43% of verified answers were wrong. A failing test or a Docker build error is often only the symptom, and rules and model agreed on that symptom.
  - The model's self-reported confidence (0.90–0.98 on wrong answers) made this worse.
- **Decision:**
  - **Evidence validity** ("N of M citations found on their cited lines") is reported on its own and never decides the cause status.
  - **Root-cause status** has new values:

    | status | when |
    |---|---|
    | `corroborated` | every citation is genuine, a cited log line *states* a cause of the claimed kind (D-041), the log states no competing cause, and the rules do not point elsewhere |
    | `plausible` | grounded and consistent, but the cause is not confirmed; the note says why: only a symptom is shown, the stated cause is not cited, another cause is also stated, the rules point elsewhere, or a citation was rejected |
    | `conflicting` | the log states a different underlying cause, or strong signature evidence points elsewhere. A test regression never stands against a stated environmental cause |
    | `not_established` | the model declined, or the claim failed a check |

    Even `corroborated` is presented as "strong evidence, not proof".
  - **Confidence:** the UI no longer shows the model's confidence. It shows the status, a plain explanation of it, the evidence check, and the verifier's notes. The confidence column is kept for analysis, capped per status (0.9 / 0.6 / 0.3 / 0.1).
  - **Existing records:** migration `0007` relabels them conservatively, because no cause check ever ran on them:
    - verified and supported become plausible
    - contradicted becomes conflicting
    - unknown becomes not_established

    Each relabelled row gets a note.
  - **What only `corroborated` earns:** incident indexing. Remediation proposals still require `corroborated` or `plausible`.
- **Why:** a status a reader trusts must mean more than "the quotes are real". The new names say what was checked and what was not.

### D-041: Cause-level evidence, and causes outrank the symptoms that report them (M5.1)
- **Status:** accepted (2026-10-30)
- **Decision:** `kensa.analysis.causes` finds lines that *state* an underlying cause, over the whole log:
  - a variable that must be set, a `KeyError` on an upper-case name, an unbound shell variable, an unresolved placeholder, a missing action input
  - an empty variable in a step's `env:` dump (GitHub masks a set secret as `***`)
  - permission refusals (`permission_denied`, "Resource not accessible by integration")
  - database refusals and authentication failures
  - Docker daemon, pull and build-context errors
  - missing paths
  - dependency resolution, lockfile and compile errors
  - memory, disk and time limits
  - assertion mismatches, for test regressions
- **Exclusions:**
  - Variable names are case-sensitive.
  - A line a test asserts on is data under test, never a statement about the environment.
  - Failing-test summaries and Docker build wrappers ("failed to solve") are symptoms, not causes.
- **Uses:**
  - **Classifier:** a stated cause scores like a strong signature. When an environmental cause is stated, the symptom signatures of other categories count with weight 1.
  - **Verifier:** decides `corroborated` (D-040).
  - **Prompt:** gets one rule ("name the underlying cause, not the symptom") and Kensa's findings as line numbers by category, never as log text.
- **Development and limits:**
  - The patterns were written from the category definitions and general knowledge of tool messages. They were checked on the v1 dev split and then on the v2 dev split.
  - The idea came from the M5 failure review of the v1 test split, at the owner's request. That split is spent and is not used for any measurement.
  - A finding is evidence, not proof: an incidental warning that matches a cause pattern can mislead the classifier. The v2 "lookalike" cases measure this.

### D-042: Evaluation set v2: 60 dev and 60 held-out cases, independent author, frozen before use (M5.1)
- **Status:** accepted (2026-10-30)
- **Decision:**
  - **Authorship:** a separate LLM author writes every case and label under `eval/datasets/v2/AUTHORING_SPEC.md`, isolated from Kensa's code, documents, v1 and reports. Kensa's development supplied the spec, the per-case plan and the gates, but no case content or labels.
  - **Plan:** the same distribution in each split (`plan.csv`):
    - 32 standard cases (4 per category)
    - 12 masked: the cause hides behind a test, build or script failure
    - 6 misleading
    - 4 lookalike: wording suggests another category
    - 6 insufficient: generic exit, truncated log, two equally plausible causes
  - **Ground-truth rule:** the category is what must change to fix the failure.
  - **Gates** (`scripts/freeze_dataset.py --dataset v2`):
    - plan conformity, exact evidence ranges and log length
    - repository files including the workflow
    - no credential-like strings, no line naming the cause or addressing a model
    - no templating within v2 or against v1, using an explicit boilerplate allowlist. v1 keeps its original gates unchanged.
  - **Held-out discipline:** the output names case ids only, so running the gates never shows test content. Test cases are not opened during development.
  - **Order:** all 120 cases are frozen before any evaluation. The dev split is used for development; the test split is run once, under a protocol committed beforehand.
  - **Baseline:** the M5 system (`d7c6f56`) runs from a detached worktree. Only its harness is patched, to load v2 into its own database (`eval/reports/m51-baseline-harness.patch`).
- **Why:** v1's test split is spent (D-039), and 20 cases per split could not separate configurations.

### D-043: Dependency scans run, nothing upgraded (M5.1)
- **Status:** accepted (2026-10-30, owner approval in the M5.1 brief)
- **pip-audit 2.10.1:**
  - Run through `uvx`, so it is not added to the project.
  - Checked the 82 pinned backend packages from `uv export --frozen`, against both the PyPI advisory data and OSV.
  - **Result:** no known vulnerabilities.
- **npm audit:**
  - Checked the 303 packages of the frontend lockfile.
  - **Result:** 0 vulnerabilities at any severity.
- **Decision:** no upgrades, since nothing is actionable. Audit finding A-6 is closed.
- **Repeating it:** before any publication, run the same two commands.

### D-044: Deterministic first: a corroborated rule-based cause replaces a model answer that established none (M5.1)
- **Status:** accepted (2026-10-31, from the v2 dev split)
- **Finding (v2 dev, development run 1):**
  - All three model configurations scored 49/60, against 55/60 for rules only.
  - On 4 dev cases the model abstained although Kensa's own cause check had corroborated the correct cause from the log alone.
  - On 2 dev cases it kept a category that conflicted with a stated cause, even after the verifier's retry feedback.
- **Decision:** `deterministic_fallback` runs after the model's final attempt in both the linear pipeline and the agent graph. It applies only when all of these hold:
  - the model's answer is not `corroborated`
  - the model established no cause, or named a different one from Kensa's rule-based diagnosis
  - that rule-based diagnosis passes the verifier as `corroborated`: the cause is stated in the log, cited, and uncontested

  Kensa then reports the rule-based diagnosis.
  - Its notes say it came from the deterministic cause check, not the model, and name the model's answer and status.
  - The model's attempts stay in the event timeline.
  - When the model named the same cause, its own (possibly hedged) answer is kept.
- **Why:** the project's "deterministic first" rule. The strictest deterministic evidence should not be discarded because a 4B model abstained or held on to a symptom.
- **Risk:** if the rules corroborate a wrong cause, the fallback turns a model abstention into a confident wrong answer. Rules-only `corroborated` was 38/38 correct on v2 dev; the held-out run measures it.
- **Held-out result (2026-10-31, `eval/reports/m51-results.md`):**
  - The fallback fired 13 times in the three model configurations. 10 abstentions or flagged answers became correct.
  - The risk happened once per configuration: on t27 it turned an abstention into a wrong `corroborated` test regression.
  - See D-045. Since D-046 (M5.2) the fallback can no longer report a test regression.

### D-045: After the v2 held-out result: report, do not tune; the v2 test split is spent (M5.1)
- **Status:** accepted (2026-10-31)
- **Result** (`eval/reports/m51-results.md`):
  - **Accuracy:** M5.1 41–44/60 against M5's 28–41/60. Wrong answers fell from 9–10 to 3 in the full-text configurations.
  - **Primary trust measure, not met:** wrong strongest-status answers rose from 0–1 (`verified`, M5) to 2–3 (`corroborated`, M5.1) per configuration. `corroborated` was right 88–90% of the time, against 100% on dev.
  - **Where they came from:** every wrong `corroborated` answer was a `test_regression`, corroborated by an assertion line while the log's real cause was stated in wording the patterns do not know (t16, t27), or while the log showed no cause at all (t47).
  - **Every other category held:** `corroborated` was right 60 of 60 times for every other category; for `test_regression` it was right 14 times and wrong 9.
  - **Unchanged:** citations are all genuine (646/646 re-checked), and latency did not regress.
- **Decision:**
  - **No change in response to the test answers:** no pattern for curl's or Neo4j's wording, no change to the verifier or the fallback.
  - **The v2 test split is spent:** any future result on it is not a held-out result and must be labelled as such.
- **Proposed, for the owner to decide** (the owner chose it on 2026-11-01; implemented as D-046):
  - An assertion line should never by itself corroborate a cause, because it states a symptom. `test_regression` would then be at most `plausible` without positive evidence pointing at the code under test, and the deterministic fallback would no longer report it.
  - This is a principle rather than a pattern. Its effect needs a new independent set (v3) to measure; on v2 dev it can only be checked for regressions.
- **Why:** the same as D-039. A result reported honestly, and an unused next held-out set, are worth more than fixing the two cases the test split exposed.

### D-046: A test regression is never corroborated; an assertion is a symptom (M5.2)
- **Status:** accepted (2026-11-01, owner chose M5.2 after reviewing M5.1)
- **Decision:** the verifier never gives `corroborated` to a `test_regression` claim; it stays at most `plausible`.
  - **The note says why:** "a failing assertion shows that a test failed, not why: the log cannot show that the code under test changed, and a cause stated in unfamiliar wording would not be recognised".
  - **Unchanged:**
    - all other categories and every other check
    - the classifier and the cause patterns
    - the prompt, the model calls and retries (retries depend on `retryable`, which neither status sets)
- **Effects:**
  - The deterministic fallback (D-044) only reports `corroborated` diagnoses, so it can no longer report a test regression.
  - Test regressions are no longer indexed as past incidents.
  - Their stored confidence cap is 0.6.
- **Why:**
  - On the v2 held-out split every wrong `corroborated` answer (9) was a test regression, against 60/60 right for every other category (D-045).
  - The mechanism is general, not tied to those cases. An assertion states that an expectation failed. "No competing cause" only means none was recognised, and real logs contain wordings no pattern knows.
  - Adding the missed wordings instead would have been tuning on the test answers.
- **Cost:**
  - A real test regression is now reported as `plausible` ("a hypothesis"), never `corroborated`.
  - A fallback that used to rescue a correct test regression from a model misled by a lookalike log no longer does: d58 on v2 dev and t58 on the spent v2 test split, each in LLM + full text only.
- **Evidence** (`eval/reports/m52-results.md`):
  - **v2 dev, one run of the four configurations:**
    - No wrong answer is `corroborated`.
    - Correct: 55/52/53/53, against M5.1's 55/54/54/53. Of the 3 lost answers, 1 is D-046's (d58) and 2 are model run-to-run variation (d51; d58 in agent + full text).
  - **Spent v2 test split, derived exactly from M5.1's stored run** (labelled as not a held-out result):
    - Wrong `corroborated` answers fall from 2–3 to 0 per configuration.
    - Correct answers go from 41/44/44/44 to 41/43/44/44.
  - **Its effect on new cases is unmeasured** until a new independent set exists.

### D-047: Japanese UI without an i18n library (M6)
- **Status:** accepted (2026-11-02, approved with the M6 plan)
- **Decision:** the en/ja toggle uses Kensa's existing typed strings object instead of `react-i18next`, which the original plan named.
  - `ja.ts` must satisfy the type `Messages`, the English object widened to plain strings, so a missing key fails the build.
  - A test checks that every placeholder matches and that every string is translated, except names.
  - A small React context provides `useStrings()` and `useLocale()`. The choice is stored like the theme and sets `<html lang>`.
  - Dates are formatted in the UI's language, not the browser's.
- **Model output stays English:** diagnoses, evidence, verifier notes and timeline entries are data or model output, not UI strings. A Japanese note says so. Translating them would need another model call, or translating the evidence itself.
- **Authoring:** `ja.ts` was drafted from a fixed glossary and style rules; every string was then reviewed, and six were changed.
- **Why:** less code than the library, no new dependency, and the same compile-time completeness guarantee. Plurals and other library features are not needed by these strings.

### D-048: A static replay build of recorded runs, instead of a demo Compose profile (M6)
- **Status:** accepted (2026-11-02)
- **Decision:** the demo is a static build of the real UI (`npm run build:replay`) that answers from real runs recorded once with the local model. This replaces the planned Compose profile with the mock provider.
- **Recording** (`scripts/record_replays.py`):
  - The real app runs in its production settings (agent graph, hybrid retrieval, the local model) against its own `kensa_replay` database, and is driven over HTTP.
  - Dev-split cases are created through the same service the API uses, with their repository files, and without the dataset's titles, which hint at the answer.
  - Nothing is written if any recorded string matches the secret, signed-URL or local-path checks.
  - The manifest records the date, commit, model, context size and GPU.
- **Replay behaviour:**
  - One branch in `lib/api/client.ts` answers GETs from the recording.
  - Approve and reject change an in-memory copy by the backend's rules (409 on a conflicting decision). Because no agent resumes, the status goes straight to completed, and no events are invented.
  - Everything else is refused, and creating investigations is disabled with a notice.
  - Every page carries a banner naming the recording date, model and GPU.
- **Why:**
  - A recruiter can see real model output and the real UI without Docker, Ollama or a GPU.
  - The mock provider would have shown rule output only.
  - Hash routing and relative paths make it hostable anywhere static, should the owner ever approve publishing it.
- **Cost:**
  - Recordings go stale when the API changes. The replay e2e test fails then, because the UI's type guards check every recorded response.
  - The normal build carries the small adapter as an unused chunk; the recording itself ships only in the replay build.
- **Amendment (2026-11-03, the owner's M6 requirements):**
  - **Authenticity is checked, not assumed:**
    - `backend/tests/test_replay_recording.py` compares every recorded log line, evidence block, signature and citation with the source files. It does not use Kensa's verifier, and it runs in CI.
    - `record_replays.py --verify` confirms the file is exactly what the API returns for the runs stored in `kensa_replay`.
    - Nothing in the recording is edited by hand. The weak test-regression proposals stay as recorded.
  - **Temporary approvals are labelled before the decision too:** a note above the buttons, also attached to them as their accessible description. After the decision, "Not saved".
  - **Offline is tested:** `replay.spec.ts` blocks every request outside the replay's own files. `npm run e2e:replay` runs the replay tests with no backend, database or model.

### D-049: MIT licence; third-party notices generated from local metadata (M6)
- **Status:** accepted (2026-11-02, approved with the M6 plan)
- **Decision:** Kensa's code is MIT ("Copyright (c) 2026 Akshat Mishra"). `THIRD_PARTY_NOTICES.md` is generated by `scripts/third_party_notices.py` from local metadata only:
  - Python: uv.lock and the installed metadata.
  - Frontend: `npm ls --omit=dev` and each package's own licence file. These packages are bundled into the built app, so their full texts are included.
  - Models: the local Ollama manifests.
- **Findings:**
  - Three LGPL-3.0 packages (psycopg). They are installed separately by uv and used unmodified, which is compatible with an MIT project that does not copy them.
  - Every frontend package is MIT.
  - The chat model's manifest carries Apache 2.0. The embedding model's manifest states no licence, so the notices say so rather than guess. Its upstream licence is to be checked before any publication.
- **Why:** the licence must be clear before publication, and attributions must come from evidence, not memory.
- **Amendment (2026-11-03): licences checked upstream** (public pages, read by hand; the script still reads no network):
  - **`qwen3:4b-instruct-2507`:** Apache-2.0 on its Hugging Face model card, which matches the local manifest.
  - **`qwen3-embedding:0.6b`:**
    - Apache-2.0, from the publisher's own sources. The Qwen Team's announcement (2025-06-05) releases the series "under the Apache 2.0 license on Hugging Face and ModelScope", and the model card under the official Qwen organisation declares `apache-2.0`.
    - The announcement's word "proprietary" means Qwen's own model. Neither repository ships a LICENSE or NOTICE file, and Ollama's package states no licence.
    - Kensa never distributes the weights, so the notices record the licence and its source.
  - **pgvector:** the PostgreSQL License (its LICENSE text). **Ollama:** MIT.
  - **Two corrections:**
    - Packages that hold only type declarations (`@types/react`, `@types/react-dom`, `csstype`) are no longer listed as bundled.
    - The MPL-2.0 packages (certifi, part of orjson) are noted as used unmodified, like the LGPL ones.
  - Kensa's MIT licence is compatible with all of them as used.

### D-050: A clean publication snapshot, pinned Actions and a manual Pages workflow (publication preparation)
- **Status:** accepted (2026-11-03, the owner's decisions)
- **Decision:**
  - **A new history.**
    - The public repository is a snapshot of chosen files at one commit of the development history, committed again as a single new commit.
    - The development history stays private and unchanged. It holds a local path in three commits, and working notes.
  - **What is left out:**
    - development-tool configuration and the private working notes
    - the authenticated M4 live-run reports, which hold a real repository's logs
    - the snapshot script itself
  - **How it is made:** `scripts/make_release.py` copies the committed tree, minus those files, and fails if any of these survive:
    - a private file name or a private repository name
    - a personal path
    - a broken relative link
  - **Rewording happens at the source:** public files that referred to private ones were reworded in the development repository, so the snapshot copies files and never rewrites them.
  - **Actions pinned:** every action is pinned to a full commit SHA, checked against its release tag with `git ls-remote`.
  - **Least privilege:**
    - `ci.yml` has `contents: read` only.
    - `pages.yml` runs only when started by hand. Its single write permission (`pages`, `id-token`) belongs to its deploy job.
    - `test_ci_workflow.py` enforces all of this.
  - **Notices with the replay:** the replay build ships `THIRD_PARTY_NOTICES.txt`, generated with the other notices and linked from every page.
- **Why:**
  - Rewriting the development history would destroy the record, while publishing it would publish the notes and the path.
  - A snapshot publishes only what was chosen.
- **Cost:** commit IDs quoted in the public docs and reports refer to the private history.
- **Amendment (2026-11-08, v1.0 publication approved by the owner):**
  - The snapshot is published as a public repository, with the replay demo on GitHub Pages.
  - Wording that named development tools was removed from the public files and report headers. No method, measurement or result changed.
  - The two frozen dataset notes (`eval/datasets/v1/AUTHORING.md`, `eval/datasets/v2/AUTHORING.md`) keep their original wording, because the freeze manifests cover them and every report cites those digests.
  - The snapshot check also fails on development-tool names outside those two notes, and allows the account name only in the repository and demo addresses.
  - The replay banner calls the demo a prerecorded interactive replay, not live AI inference.
  - The replay e2e tests take `KENSA_REPLAY_URL`, so the same 10 tests can check a deployed copy of the demo.

### D-051: A provenance ladder, and history that can never confirm itself (v1.1)
- **Status:** accepted (2026-11-09, part of the v1.1 plan approved by the owner)
- **Decision:** every derived statement says where it comes from:

  | provenance | meaning |
  |---|---|
  | `observed` | a log line, diff hunk or run status read from GitHub or a pasted log |
  | `rule_derived` | a signature, cause or fingerprint found by rules |
  | `model_hypothesis` | model output |
  | `verifier_corroborated` | the verifier found the log states the cause |
  | `human_confirmed` | the operator confirmed it (an audited request) |

  - Only log causes corroborate. History, diffs and confirmed resolutions never raise a status.
  - `data_origin` (`github_live`, `pasted`, `sample`, `eval_synthetic`, `replay`) keeps real observations apart; analytics count only the first two unless asked.
  - `index_incidents` now defaults to off: a model conclusion no longer becomes evidence for the next investigation. Similar failures appear in a separate History panel instead.
- **Why:** a wrong diagnosis indexed as an "incident" competed with real evidence for the next run of the same failure, an anchoring loop.
- **Cost:** a corroborated past diagnosis no longer reaches the model as evidence. Whether human-confirmed resolutions help as hints is left as a measured experiment (not done in v1.1).

### D-052: History ingestion: incremental, idempotent, budgeted, outside the agent worker (v1.1)
- **Status:** accepted (2026-11-09)
- **Decision:**
  - Tracked public repositories are synced by a dedicated history worker. The agent worker never syncs and stays network-free (D-031).
  - Runs and jobs are upserted on natural keys (`ON CONFLICT DO UPDATE ... WHERE IS DISTINCT FROM`), so a re-sync changes nothing that did not change.
  - A cursor in `sync_state` (`complete_through`, the current window and page, pending work) lets an interrupted sync resume.
  - Every sync has a request budget (default 300). On a rate limit or an exhausted budget the batch ends as `partial` or `rate_limited`; nothing reschedules itself.
  - Commit authors, e-mail addresses and actor logins are never stored.
  - Data-quality checks record findings by key (first seen, last seen, resolved).
  - **Forget repository** and **retention** are full cascades (the owner's correction 3): investigations with every derived record, checkpoints, incident and diff documents, fingerprint links and unreferenced fingerprints, analytics rows, findings and snapshots. A meta-test fails if any table with `workspace_id` is not covered. Only non-reconstructable counts remain, in `purge_audits`.
- **Why:** history must be cheap to keep current, safe to re-run, and impossible to turn into a reconstructable record of something the owner asked to forget.

### D-053: Failure fingerprints are rule-derived and versioned; similar failures are history, not evidence (v1.1)
- **Status:** accepted (2026-11-09); version 2 the same day
- **Decision:**
  - A fingerprint hashes `version | category | rule | normalised subject | masked template`, built only from signatures and stated causes, never from model output.
  - Masks remove what varies between recurrences: timestamps, SHAs, UUIDs, numbers, durations, sizes, temporary and runner paths, source positions, long quoted literals.
  - **Version 2** (developed on the v3-history dev split only):
    - no primary from a generic rule (GitHub's `##[error]` annotation, an exit code)
    - context only for a line that names no failure by itself; the step names a time-out, the pulled image names a pull failure
    - test-regression templates keep assertion values; source positions are always masked
  - Similar failures: same primary fingerprint first, then related (secondary) fingerprints, then similar wording. They are shown with their provenance and never enter the evidence or the prompt.
  - A human-confirmed resolution is an audited record that can never change a verification status.
- **Why:** recurrence detection is a deterministic problem, and a model-derived key would let history confirm itself.
- **Cost:** two causes that differ only in values (one test failing for two reasons) get different fingerprints, or the same one when the values happen to match. Rules cannot separate them; precision was preferred.

### D-054: Change-aware investigation: factor-based comparability, ranked suspects, correlation only (v1.1)
- **Status:** accepted (2026-11-09)
- **Decision:**
  - At import, Kensa looks for the last successful run of the same workflow before the failure and compares the two (GitHub's compare API, a budget of 8 requests).
  - **Comparability is factor-based** (the owner's correction 2): workflow-file identity, event, branch, job, runner labels and runner image are each `same`, `different`, `unknown` or `changed_in_range`. `comparable` needs every key factor `same`. Any `unknown` gives `partially_comparable`, with the unverified factors named. Unavailable information is never treated as equivalence.
  - **Precedence:** no baseline, then incomparable, then the comparison (history unavailable; behind → incomparable; identical; partially comparable; comparable).
  - **Suspects** are ranked by deterministic signals with documented weights (in the log, the subject in the diff, the change kind matching the category, size). Their status is `correlated` or `weak`, enforced by a CHECK constraint; "cause" is not a value.
  - **Diff hunks** become redacted, citable documents. The verifier accepts them as support, never as corroboration.
  - The analysis runs at import; the graph node `collect_changes` only reads it, so the worker stays network-free.
- **Why:** "what changed since it last worked" is the strongest lead a human uses, but a correlation stated as a cause would be exactly the confident wrong answer Kensa exists to avoid.

### D-055: Analytics: one incrementally refreshed daily aggregate on PostgreSQL; SVG charts (v1.1)
- **Status:** accepted (2026-11-09)
- **Decision:**
  - `analytics_daily` holds runs, failures, investigations, corroborated counts and latency percentiles per day, repository, workflow, category and origin.
  - A refresh recomputes whole days (delete and insert in one transaction), so refreshing a day twice gives the same rows. Days are refreshed when a sync touches them, or when investigations changed since the workspace's watermark.
  - The dashboard is one API response. Charts are hand-written SVG, each in a figure with a caption and an equivalent data table (D-047: no chart library).
  - The escalation rule stays: DuckDB or Parquet only if PostgreSQL fails the load benchmark after indexing.
- **Why:** the data is small (a busy repository is tens of thousands of rows a year), and one datastore keeps purges and transactions simple.

### D-056: v3 evaluation: independent validation before the freeze; Hit@1 and MRR for culprit ranking (v1.1)
- **Status:** accepted (2026-11-09)
- **Decision:**
  - Before freezing, a separate validator task labels items blind and compares: every gate- or author-flagged item, plus a seeded 20% sample of each split. Disagreements get one author revision and one fresh re-validation; items still disputed are excluded. The rules were fixed before the verdicts were read.
  - The culprit-ranking thresholds use Hit@1 and MRR against two naive baselines. Hit@3 is reported only: the cases change 2–5 files, so every ranking reaches about 1.0 (seen on dev).
  - Thresholds are in `eval/reports/v11-protocol.md`, committed before any test split ran.
- **Why:** the owner's correction 4, and a metric that can tell rankings apart.

### D-057: Fingerprint version 3: exact recurrences only from named subjects; similarity is never a recurrence (v1.1.0)
- **Status:** accepted (2026-11-10, after version 2 missed its held-out thresholds; the owner's v1.1.0 instructions)
- **Decision:**
  - **Two kinds.** An *exact* fingerprint is built from a subject the log names (variable, module, package, test with its assertion, image, file, port, database, permission, compile symbol), or from a line that still holds a distinctive identifier after masking. Only a shared exact primary fingerprint is shown as a **recurrence** ("same failure"). Everything else is *approximate* and only helps find *similar* failures, in a separate list that says it is not confirmed.
  - **Rule families.** Rules reporting the same kind of fact share a key, so a recurrence reported through one rule in one run and another rule in the next still matches.
  - **Where the failure is named.** Summaries point back to the error they summarise; headers (npm's code line) forward to their detail; compiler diagnostics in any language count as error lines; command echoes never do; decoration (`E`, `[error]`, yarn's prefixes) is removed before comparing.
  - **Stored kind** (`failure_fingerprints.kind`, migration 0012); analytics count recurring failures from exact fingerprints only; only the current version takes part in matching, and the backfill replaces older links.
- **Why:** version 2 met every threshold on the dev split it was tuned on and missed three on held-out data (precision 0.682). The cost of a false recurrence claim (a reader trusting a wrong earlier fix) is higher than the cost of a missed one, so precision comes first, and a generic line two causes can print is never treated as one failure.
- **Generalization, measured before tuning on it:** designed on v3-history dev only, version 3 scored precision 0.842 and recall 0.432 on the then-unseen v4-history dev split. General fixes found there raised it to 1.000 / 0.651 on that dev split.
- **Held-out result** (`v4-history` test split, 28 sequences, run once under `eval/reports/v110-protocol.md`): precision **1.000** (F1, met), recall **0.349** (F2, threshold 0.60, **missed**), look-alikes merged **0 of 22** (F3, met), similar-failure Recall@5 **0.892** (F4, threshold 0.90, **missed**), wrong "same failure" labels **0 of 15** (F5, met). Every recurrence it claimed was right; it found about a third of the true ones.
- **Consequence (the protocol's decision rule):** history matching is **experimental and off by default** (`KENSA_HISTORY_MATCHING=false`). Fingerprints are still recorded, so turning it on needs no backfill. Off: the History panel shows the fingerprint and a note, with no matches or counts; the dashboard neither counts nor lists recurring failures. On: both are labelled experimental. Whether v1.1.0 ships this way is the owner's decision.
