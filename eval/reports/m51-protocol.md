# M5.1 evaluation protocol (fixed before the v2 held-out split is run)

Written before the v2 test split is run for the first time and committed with the frozen system. Nothing below may change after that run. Any later change to Kensa is evaluated on a new set.

## Data
- **Dataset:** `eval/datasets/v2`, frozen at digest `b9ed11aff877d65e` (`MANIFEST.sha256`). The harness refuses a changed dataset.
  - The dev split was frozen on its own first (`MANIFEST.dev.sha256`, digest `56d310bdc26987fe/dev`) and used for development while the test split was still being written.
  - The final freeze checks that no dev file changed since then.
- **Authorship:** 60 dev and 60 test cases, written by a separate LLM author (`AUTHORING.md`, D-042).
  - The test cases (`t01`–`t60`) are not opened, and not run, before this protocol.
  - The dev cases are used for development.
- **Distribution per split:** 32 standard, 12 masked, 6 misleading, 4 lookalike, 6 insufficient.

## Systems
- **M5 baseline:** commit `d7c6f56`, run from a detached worktree.
  - Only its evaluation harness is patched (`m51-baseline-harness.patch`): the v2 path and case kinds, its own `kensa_eval_m5` database, and per-split loading and freezing. No rule, verifier, prompt or graph code differs from M5.
  - It gets the same model settings from `.env` as M5.1.
  - Its statuses use the M5 vocabulary.
- **M5.1:** the commit recorded in the reports (`Git:` line), frozen before the test run. It includes:
  - the root-cause statuses (D-040)
  - cause-level evidence and its precedence (D-041)
  - the deterministic-first fallback (D-044)

  No rule, pattern, prompt, threshold or weight changes between the last dev run and the test run.
- **Same conditions:**
  - local model `qwen3:4b-instruct-2507-q4_K_M` (temperature 0, seed 42, `num_ctx` 8192, `num_gpu` 99)
  - embeddings `qwen3-embedding:0.6b`
  - no GitHub access
  - GPU state sampled every 30 s

## Configurations (`--configs m51`)
| name | provider | retrieval | runner |
|---|---|---|---|
| rules-only (M3 agent) | rules, no model | signature + full text | agent graph |
| llm + fts | local model | full text | linear pipeline |
| agent + fts (M3) | local model | full text | agent graph |
| agent + hybrid (M3) | local model | signature + full text + vector | agent graph (the production configuration) |

## Metrics (per system and configuration; `scripts/m51_analysis.py`)
- **Correct:** the predicted category equals the label (for insufficient cases, `unknown`). Reported with a 95% Wilson interval.
- **Incorrect:** a category other than `unknown`, and wrong. Reported by status:
  - **incorrect with the strongest status:** `corroborated` (M5.1) or `verified` (M5). This is the primary trust measure, the "incorrect confident answer".
  - **incorrect, hedged:** `plausible` or `supported`
  - **incorrect, flagged:** `conflicting` or `contradicted`
- **Strongest status correct:** the share of answers with the strongest status whose category is right.
- **Abstentions:** correct (an insufficient case) and missed (a case with a known cause). Insufficient-evidence detection is reported separately.
- **Citation validity:** accepted over generated citations in the final answer.
- **Latency:** wall time per case and model-call time (p50/p95), read together with the GPU samples.
- **Accuracy by kind:** standard, masked, misleading, lookalike, insufficient. Lookalike accuracy is the over-correction check.

## Primary questions (stated in advance)
1. Do fewer wrong answers carry the strongest status in M5.1 than in M5, on the same unseen cases?
2. When M5.1 says `corroborated`, how often is it right?
3. Do masked cases improve, without lookalike or standard cases getting worse?
4. Is there a latency regression in any configuration beyond what GPU state explains?

Overall accuracy is reported, but it is not the target.

## Limits stated in advance
- **The data:** 60 synthetic cases per split from one independent author. Differences of 3–4 cases are within noise; intervals are shown.
- **Development:** the cause patterns (D-041) were developed on the v1 and v2 dev splits. Their direction came from the M5 review of the spent v1 test split, which is not used for any measurement.
- **Labels:** the category is the proxy. Root-cause wording is not scored automatically; wrong answers are reviewed after the run, for reporting only.
- **Remediation:** no validated diff is claimed to be semantically correct or safe.

## Afterwards
Results are reported as measured. Nothing is tuned against the v2 test answers, and the v2 test split is then spent.
