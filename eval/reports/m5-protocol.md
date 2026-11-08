# M5 held-out evaluation protocol (fixed before the test split is run)

Written and committed **before** the held-out test split is run for the first time. Nothing below may change after the run. Any change to Kensa after the run is evaluated on a new, separate set (see "Afterwards").

## Data
- **Dataset:** `eval/datasets/v1`, frozen at digest `207bde74cb9585d4` (`MANIFEST.sha256`; the harness refuses a changed dataset).
- **Test split:** 20 held-out cases, written in M2 by a separate LLM author and untouched since. They have not been opened, inspected or run before this protocol.
- **Dev split:** the same 20 dev cases as M2 and M3. They are run under the same frozen system for a dev-to-test comparison.

## System
- The Kensa commit recorded in each report (`Git:` line), frozen before the test run. No prompt, rule, vocabulary, weight or threshold is changed between the dev and test runs.
- **Local model:** `qwen3:4b-instruct-2507-q4_K_M` (temperature 0, seed 42, `num_ctx` 8192, `num_gpu` 99).
- **Embeddings:** `qwen3-embedding:0.6b`.
- **No GitHub access:** the evaluation never contacts GitHub, and the owner's token is not used.

## Configurations (`scripts/evaluate.py --configs m5`)

| name | provider | retrieval | runner |
|---|---|---|---|
| rules-only (M3 agent) | rules, no model | signature + full text | agent graph |
| llm, no retrieval (log tail) | local model | none: only the last step chunks of the log reach the model | linear pipeline |
| llm + fts | local model | full text only | linear pipeline |
| llm + hybrid (M2) | local model | signature + full text + vector | linear pipeline |
| agent + fts (M3) | local model | full text only | agent graph (completeness gate, verifier loop, planner) |
| agent + hybrid (M3) | local model | signature + full text + vector | agent graph (the production configuration) |

## Metrics (per configuration, reported separately)
- **Correct:** the predicted category equals the labelled category. For insufficient-evidence cases the label is `unknown`.
- **Incorrect (false diagnosis):** the prediction is a category other than `unknown`, and wrong.
- **Abstention:** the prediction is `unknown`. Reported in two parts:
  - correct abstention: an insufficient-evidence case
  - abstention on a case with a known cause, which is a missed diagnosis
- **Insufficient-evidence detection:** insufficient cases answered `unknown`, as a share of all insufficient cases.
- **False confidence:** incorrect, *and* presented as an established cause (status `verified` or `supported`). Also reported: incorrect with confidence ≥ 0.5.
- **Grounded but wrong:** incorrect, *and* at least one accepted citation that comes from the run's own log. That means genuine evidence was cited, but the root cause is wrong. "Verified but wrong" (status `verified`) is reported too.
- **Citation validity:** accepted over generated citations in the final answer. For the agent, also across all attempts.
- **Latency:** wall time per case (p50/p95), model-call time (p50/p95), and Ollama's timing breakdown from the local traces (load, prompt evaluation, generation, tokens/s).
- **Also reported:** accuracy by case kind (standard / misleading / insufficient), verified count, fix-keyword hits (a weak proxy for remedy quality, not a correctness measure), proposals and diffs.

## Limits stated in advance
- **Small sample:** 20 synthetic cases per split, so differences of 1–2 cases are not meaningful.
- **Root-cause wording is not scored automatically;** the category is the measured proxy. Wrong answers are reviewed by hand *after* the run, for reporting only.
- **No validated patch is claimed to be semantically correct or safe.** Diffs are only mechanically checked.

## Afterwards
If the held-out results expose weaknesses, they are reported as measured. Kensa is not tuned against the test answers. Any further optimisation needs a new evaluation set (v2) written independently, with its own frozen dev/test split.
