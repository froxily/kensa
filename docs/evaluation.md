# Evaluation: method and results

Kensa is judged on whether it names the right root cause, and on whether its confidence can be
trusted. Every number here was measured on one laptop (RTX 3050 Laptop GPU, 4 GB) with the local
model `qwen3:4b-instruct-2507` (Q4_K_M). The full reports, with raw per-case rows, are in
[`eval/reports/`](../eval/reports).

## Method

**Independent data.** Both evaluation sets were written by a separate LLM author working in
isolation, from a specification and quality gates written during development, without access to
Kensa's code
([v1](../eval/datasets/v1/AUTHORING.md), [v2](../eval/datasets/v2/AUTHORING.md)).

| Set | Dev | Test | What the cases are |
|---|---|---|---|
| v1 | 20 | 20 | Failed GitHub Actions logs across 8 categories, plus insufficient-evidence cases |
| v2 | 60 | 60 | The same categories, with a fixed mix per split: 32 standard, 12 masked (the cause hides behind a failing test or Docker build), 6 misleading, 4 lookalike, 6 insufficient |

**Frozen before use.** Each set is frozen by a hash manifest. The harness refuses to run a set that differs from its manifest, and every report states the digest.

**Where each split stands (2 November 2026):**

| Split | Used for | Status |
|---|---|---|
| v1 dev (20) | Development and comparisons, M2 to M5 | Development data |
| v1 test (20) | One held-out run, M5 (2026-10-31) | **Spent** |
| v2 dev (60) | M5.1 development; the M5.2 regression check; 3 cases in the M6 replay | Development data |
| v2 test (60) | One held-out run, M5.1 (2026-10-31); M5.2 derived from that run without running the model | **Spent** |

The v3 sets (v1.1, below) added new splits: their dev splits are development data, and their test splits were each run once on 2026-11-09 and are now **spent**.

**Dev for development, test once.**
- Changes were compared on the dev split only.
- The test split was run once per system, under a protocol committed beforehand ([M5](../eval/reports/m5-protocol.md), [M5.1](../eval/reports/m51-protocol.md)).
- After that run, the split is **spent**. Nothing is tuned on its answers, and any later number on it is labelled "not a held-out result". Both test splits are now spent.

**Configurations.** The same cases run through several systems, from the deterministic rules alone to the production setup:

| Configuration | What runs |
|---|---|
| rules only | Signature rules, no model |
| LLM + full text | One model call on full-text retrieval |
| agent + full text | The LangGraph agent, full-text retrieval |
| agent + hybrid | **The production setup:** the agent, with signature, full-text and vector retrieval fused |

**Metrics** (defined in the protocols):
- correct category, with a 95% Wilson interval
- wrong answers, split by the status they carried
- how often the strongest status was right
- correct abstentions, and missed causes
- citation validity, re-checked independently against the stored text
- latency, sampled together with the GPU's clock, power limit and throttling

## Results

| Milestone | Cases | Result |
|---|---|---|
| M0 | 5 fixtures | The model fits fully on the 4 GB GPU at 8K context: ~50 tok/s, 3.7 GB peak VRAM ([report](../eval/reports/m0-model-benchmark-numgpu99.md)) |
| M2 | v1 dev, 20 | Recall@10: full text 0.580, hybrid 0.559, vector 0.451. Hybrid was **not** better than full text ([report](../eval/reports/m2-retrieval-dev-ollama.md)) |
| M3 | v1 dev, 20 | Agent + hybrid 20/20, agent + full text 16/20 ([report](../eval/reports/m3-diagnosis-dev-ollama.md)) |
| **M5, held out** | v1 test, 20 | 11–13/20 in every configuration (dev: up to 20/20). Answers labelled "verified" were right only 57–78% of the time ([results](../eval/reports/m5-results.md)) |
| **M5.1, held out** | v2 test, 60 | 41–44/60 (M5 on the same cases: 28–41), with all 646 accepted citations genuine. **The primary trust goal was not met:** 2–3 wrong answers per configuration were marked `corroborated` (M5 gave its strongest status to 0–1 wrong answers on the same cases), all of them test failures taken as the cause. `corroborated` was right 88–90% of the time ([results](../eval/reports/m51-results.md)) |
| M5.2 | v2 dev, 60; v2 test (spent) | A test regression is never `corroborated` (D-046). Dev: 55/52/53/53 (M5.1: 55/54/54/53), no wrong `corroborated`. On the spent test split, derived exactly from the stored run, wrong `corroborated` answers fall from 2–3 to 0 per configuration, and correct answers go from 41/44/44/44 to 41/43/44/44 ([results](../eval/reports/m52-results.md)) |

## v1.1: change-aware investigation and failure history (v3 sets)

**New independent sets.** v1.1's features needed new data, so two v3 sets were written by a separate LLM author, isolated from Kensa's code, validated independently before the freeze, and frozen ([v3-change](../eval/datasets/v3-change/AUTHORING.md), [v3-history](../eval/datasets/v3-history/AUTHORING.md)). Thresholds were fixed beforehand in [the v1.1 protocol](../eval/reports/v11-protocol.md); each test split ran once.

| Set | Dev | Test | What the items are |
|---|---|---|---|
| v3-change | 28 | 30 | A failed run, its earlier runs, the changes between them and a repository snapshot; labelled comparability, unverified factors, category and culprit |
| v3-history | 19 sequences (76 logs) | 18 sequences (72 logs) | Four failures of one repository over time, labelled by cluster (same cause, same fix), including look-alikes |

**Independent validation.** A separate validator labelled every flagged item and a seeded 20% sample blind, then compared. Disputed items got one revision and one re-validation; 5 items still disputed were excluded (2 change, 3 history) before the freeze.

**Held-out results** ([v1.1 results](../eval/reports/v11-results.md); each test split run once):

| What | Threshold | Held-out | Dev |
|---|---|---|---|
| Culprit Hit@1 (change analysis, 21 culprit cases) | above both naive baselines | **0.810** (largest diff 0.476, most recent 0.238): met | 0.789 |
| Culprit MRR | above both baselines | **0.905** (0.706, 0.571): met | 0.895 |
| Comparability verdict (30 cases) | ≥ 0.90 | **1.000**: met | 1.000 |
| A suspect stated as a cause; a correlated suspect without a culprit | never | never: met | never |
| Fingerprint pairwise precision (72 entries) | ≥ 0.90 | **0.682: not met** | 1.000 |
| Fingerprint pairwise recall | ≥ 0.60 | **0.469: not met** | 0.943 |
| Similar-failure Recall@5 (25 recurrences) | ≥ 0.90 | **0.960**: met | 1.000 |
| Look-alikes merged | ≤ 10% | **4 of 13: not met** | 0 of 13 |
| Model ablation: wrong `corroborated`, with against without change evidence (30 cases) | with ≤ without | **0 and 0**: met | 0 and 0 |
| A `corroborated` answer resting only on a diff | never | never: met | never |
| Correct category, with and without change evidence | reported | 26/30 and 26/30 (the same cases) | 29/30 and 28/30 |

- **The change analysis transferred** from dev to unseen cases; its weights were fixed before any v3 case existed.
- **The fingerprints did not.** Version 2 was tuned on the dev split and fitted its tools and wording: on unseen sequences the generic "last error line" fallback carried twice the share it had on dev, and recurrences sometimes picked different rules. Because similar failures are history and never evidence, a wrong match can mislead a reader of the History panel but cannot change a diagnosis. The next version needs new data to be measured.
- **Change evidence did no harm and changed no correct answer** on the held-out cases (the same 26 of 30 were right); it brought no measurable accuracy gain on these 30 cases either.
- **No regression on v2 dev:** rules-only 56/60 (v1.0: 55), agent + hybrid 53/60 (v1.0: 53), no wrong `corroborated` answer.

## v1.1.0: fingerprint version 3 on a fresh set (v4-history)

Version 2's held-out split was spent, so version 3 (D-057) was measured on a new set, [v4-history](../eval/datasets/v4-history/AUTHORING.md): 30 ecosystems, written by a separate LLM author, gated, validated independently (4 sequences excluded) and frozen with [the v1.1.0 protocol](../eval/reports/v110-protocol.md) before its test split ran once. A recurrence is claimed only when two failures share an *exact* fingerprint.

| What | Threshold | Held-out (28 sequences, 112 logs) | Dev (28 sequences) |
|---|---|---|---|
| F1 Pairwise precision | ≥ 0.90 | **1.000**: met | 1.000 |
| F2 Pairwise recall | ≥ 0.60 | **0.349: not met** | 0.667 |
| F3 Look-alikes merged | ≤ 10% | **0 of 22**: met | 0 of 21 |
| F4 Similar-failure Recall@5 (37 recurrences) | ≥ 0.90 | **0.892: not met** | 0.946 |
| F5 Wrong "same failure" labels | ≤ 10% | **0 of 15**: met | 0 of 28 |

- **Precision transferred; recall did not.** Every recurrence version 3 claimed on unseen data was right, and no look-alike was merged, but it found about a third of the true recurrences (dev: two thirds). 53 of 112 held-out logs had no exact fingerprint (dev: 34), so they could only be compared approximately.
- **Decision (fixed in advance):** history matching is experimental and **off by default** in v1.1.0 (`KENSA_HISTORY_MATCHING`). Reports: [dev](../eval/reports/v11-v4-history-dev.md), [test](../eval/reports/v11-v4-history-test.md).

## Measured, derived and not measured

| Claim | Kind of evidence |
|---|---|
| M5.1 is more accurate than M5 on new failures (41–44 against 28–41 of 60) | **Measured** on a held-out split, run once under a protocol fixed beforehand |
| M5.1's citations are genuine (646 of 646 accepted) | **Measured** on the same held-out run, and re-checked independently |
| M5.2 removes wrong `corroborated` answers (2–3 → 0 per configuration) | **Derived** exactly from M5.1's stored held-out run. The rule was chosen after seeing those answers, so this is **not a held-out result** |
| M5.2's cost: one correct answer lost in LLM + full text, on dev (d58) and on the spent test split (t58), both lookalike cases; correct test regressions shown as `plausible` | **Measured** on dev; derived on the spent test split |
| M5.2 makes `corroborated` trustworthy on failures Kensa has not seen | **Not measured.** Both v2 splits shaped the rule; this needs a new independent set (v3) |
| v1.1's change analysis ranks the breaking change above naive baselines on new cases (Hit@1 0.810 against 0.476 and 0.238) | **Measured** on a held-out split, run once under a protocol fixed beforehand |
| v1.1's fingerprints are precise on new failures | **Measured, not met:** precision 0.682 against a threshold of 0.90 (dev: 1.000) |
| v1.1.0's fingerprint version 3 claims recurrences precisely on new failures | **Measured, met:** precision 1.000 and 0 of 22 look-alikes merged (v4-history, run once) |
| v1.1.0's fingerprint version 3 finds most recurrences | **Measured, not met:** recall 0.349 against 0.60, Recall@5 0.892 against 0.90; matching is off by default |
| Change evidence adds no wrong `corroborated` answers | **Measured** on 30 held-out cases: 0 with and 0 without |
| Change evidence improves accuracy | **Not shown:** 26/30 with and without, on the same cases |
| M6 changes the diagnoses | **No:** M6 changed one timeline sentence's punctuation in the backend, and the user interface. The replay shows recorded runs; it is not a new measurement |

## Other measurements

| What | Result |
|---|---|
| M1 live check | 3 synthetic samples + 1 long log: every citation valid, 8–12 s per model call ([report](../eval/reports/m1-live-check.md)) |
| Embedding placement (M2) | `qwen3-embedding:0.6b`: 41 chunks/s on the GPU, against 0.8 on the CPU. It therefore takes turns with the LLM instead of sharing the 4 GB ([report](../eval/reports/m2-embedding-placement.md)) |
| Diagnosis, M2 (v1 dev, 20) | Rules only 15/20, LLM + signature + full text 16/20, LLM + hybrid 17/20 ([report](../eval/reports/m2-diagnosis-dev-ollama.md)) |
| GitHub, live (M4) | A real failed run in a public repository, imported with a read-only token, diagnosed `db_connectivity` with 4/4 citations. Every citation and excerpt was re-checked against GitHub's text at the run's commit. The report holds that repository's real logs, so it is not published; the anonymous check is ([report](../eval/reports/m4-live-github-anonymous.md)) |
| Security audit (M5) | Findings by severity: DNS rebinding and CSRF fixed, and 0 secrets in stored data or traces ([audit](../eval/reports/m5-security-audit.md)) |
| Dependency scans (M5.1) | `pip-audit` (82 backend packages) and `npm audit` (303 frontend packages): no known vulnerabilities |
| Dependency scans (2026-11-03) | `pip-audit`: 82 locked backend packages, no known vulnerabilities. `npm audit`: none in the packages the app ships (`--omit=dev`). 12 moderate findings in the lint tools only (ESLint, typescript-eslint), all one advisory in `minimatch` 10 (GHSA-g3hv-75wg-m249). No release of those tools has moved off `minimatch` 10 yet, and npm's offered fix is a breaking downgrade, so nothing was changed |
| Replay recording (M6; re-recorded for v1.1) | 7 runs in the production settings since v1.1 (format 2 adds similar failures, one synthetic change analysis and the dashboard; M6 recorded 6) (`frontend/replay/recording.json`), shown as recorded. `backend/tests/test_replay_recording.py` checks every stored log, evidence block, signature and all 20 citations against the source files, without Kensa's own verifier; `scripts/record_replays.py --verify` confirms the file is exactly what the API returns for the stored runs. A recording, not a measurement: model output varies between runs |

## What the numbers say
- **Dev results did not transfer in full.**
  - Agent + hybrid scored 20/20 on v1 dev (M3), and 12/20 on v1 test (M5).
  - M5.1 scored 53–55/60 on v2 dev and 41–44/60 on v2 test.
  - The held-out runs are the real results.
- **Genuine citations do not make a correct cause.** In M5, every wrong answer cited genuine lines. That is why M5.1 separated evidence validity from the root-cause status, and why `corroborated` needs a stated cause.
- **The strongest status is now trustworthy on the data Kensa has,** but not proven on new failures:
  - M5.1's held-out run showed `corroborated` test regressions to be unreliable, and M5.2 removed that path.
  - The rule was chosen after seeing those cases, so its effect on genuinely new failures is **not measured**. That would need a new independent set.
- **Abstaining is the designed failure mode.** When the log does not state a recognisable cause, Kensa says "not established" rather than guess. On the v2 test split, M5.1 missed a known cause this way 8–16 times per configuration. That is the safe failure, but it is still a miss.

## Latency
- **Diagnosis call:** about 13 s at the median at full GPU power, and 20 s while the laptop throttled the GPU to 30 W ([M5](../eval/reports/m5-results.md#latency)).
- **Hybrid retrieval doubles wall time,** because the embedding model and the LLM take turns on the 4 GB GPU.
- **Context:** every latency comparison in the reports is given with the GPU state it ran under.

## Limitations
- **The data:** synthetic cases from one separate LLM author, 60 per split at most. Differences of 3–4 cases are within noise.
- **The scoring:** the category is the proxy for the root cause.
- **The hardware:** one laptop, one model.
- **Remediation proposals** are checked mechanically (validated paths and edits), not for semantic correctness.
