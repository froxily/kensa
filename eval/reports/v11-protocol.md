# v1.1 evaluation protocol (fixed before the v3 held-out splits are run)

Written and committed before the v3 test splits run for the first time. Nothing below may change after that run. Each held-out split runs once. A later change to Kensa is evaluated on a new set, never by re-running these test splits.

## Data
- **Sets:** `eval/datasets/v3-change` and `eval/datasets/v3-history`, each frozen per split (`MANIFEST.dev.sha256`, then the full `MANIFEST.sha256`). The harness refuses a changed dataset.
  - **v3-change:** synthetic failed runs, each with its earlier runs, the changes between them (`history.json`, GitHub compare semantics), a baseline log where one exists, and a repository snapshot. Labels: comparability, unverified factors, category, culprit kind and culprit paths.
  - **v3-history:** sequences of 4 failure logs, labelled with a cluster per entry (same root cause, same fix), the relation (first, recurrence, look-alike) and the category.
- **Sizes and digests** (after validation; planned 30 + 30 change cases and 20 + 20 history sequences of 4 entries. The plan's "40 + 40 cases" for history became sequences, because pairs of entries are the unit of the history metrics):

  | Set | Dev | Test | Dev manifest | Test manifest | Whole set |
  |---|---|---|---|---|---|
  | v3-change | 28 cases (2 excluded) | 30 cases | `8ca516d5f1d950d2` | `c9b0f368c5ed12b3` | `9e036ea0f374af36` |
  | v3-history | 19 sequences, 76 entries (1 excluded) | 18 sequences, 72 entries (2 excluded) | `7e6b22ca657d41e8` | `c9e239ce17b33579` | `b182a1ed2f2b9322` |
- **Authorship:** a separate LLM author, isolated from Kensa's code, wrote every item from a fixed spec and plan (`AUTHORING_SPEC.md`, `plan.csv`).
- **Validation before the freeze (owner's correction 4):**
  - An independent validator pass (a separate task with no author context) labelled items blind, then compared. It covered every item flagged by the quality gates or by the author, plus a seeded random 20% sample of each split (`random.Random(20261109)`).
  - Items not agreed went through one author revision round and one fresh re-validation. Items still not agreed were moved to `excluded/` and count in neither split. The rules were fixed before the first verdicts were read (`AUTHORING.md`).
- **Held-out discipline:** the test items were never opened by the engineer who built Kensa. Gate messages, verdict words and disputed field names were seen; so were four author summaries (`AUTHORING.md` lists them). Nothing was tuned after those messages.

## System
- **Kensa v1.1** at the commit recorded in each report (`Git:` line), committed before the test runs. No rule, pattern, mask, weight, threshold or prompt changes between the last dev run and the test run.
- **Deterministic parts** (no model): the change analysis (`kensa.changes`: baseline choice, comparability factors, suspect ranking) and the fingerprints (`kensa.analysis.fingerprint`, version 2) with similar-failure search.
- **The model ablation:** the production agent with hybrid retrieval (signature + full text + vector), local model `qwen3:4b-instruct-2507-q4_K_M` (temperature 0, seed 42, `num_ctx` 8192, `num_gpu` 99), embeddings `qwen3-embedding:0.6b`. No GitHub access; the change analysis comes from each case's fixture through `FixtureChangeSource`, which gives exactly what GitHub's compare API would.

## Metrics and pre-registered thresholds

### v3-change, deterministic (`evaluate_v3.py --dataset v3-change`)
| id | metric | threshold |
|---|---|---|
| C1 | Culprit **Hit@1** on the cases with a labelled culprit, against the naive baselines "most recently changed file" and "largest diff" on the same cases | Kensa strictly above both baselines |
| C2 | Culprit **MRR** on the same cases | Kensa strictly above both baselines |
| C3 | Comparability verdict accuracy, all cases | ≥ 0.90 |
| C4 | Every suspect's status is `correlated` or `weak` (never a cause) | 100% |
| C5 | Cases without a culprit (identical, incomparable, no baseline, history unavailable) that show a `correlated` suspect | 0 |

Reported without a threshold: Hit@3 (it has a ceiling: cases change only 2–5 files, so every ranking scores near 1.0 on dev), unverified-factor exact match, and the breakdown per comparability.

The plan's checkpoint named "Hit@3 beats the naive baselines". It was replaced by C1 and C2 on the dev split, before this protocol, because of that ceiling.

### v3-history, deterministic (`evaluate_v3.py --dataset v3-history`)
| id | metric | threshold |
|---|---|---|
| H1 | Fingerprint **pairwise precision** (pairs of entries with the same primary fingerprint that are in the same cluster) | ≥ 0.90 |
| H2 | Pairwise recall (a floor, so that never matching anything cannot pass) | ≥ 0.60 |
| H3 | Similar-failure **Recall@5**: for each recurrence, an earlier entry of its cluster is among the 5 similar failures | ≥ 0.90 |
| H4 | Look-alikes whose primary fingerprint equals an earlier entry of another cluster | ≤ 10% of look-alikes |

### v3-change, model ablation (`evaluate_v3.py --dataset v3-change --llm`)
Two configurations on the same cases: **with changes** (the change analysis saved, its notes in the prompt, its diff hunks as citable evidence) and **without changes**.

| id | metric | threshold |
|---|---|---|
| L1 | Wrong answers with the status `corroborated` | with changes ≤ without changes |
| L2 | `corroborated` answers whose only valid citations are diff hunks (a diff never corroborates) | 0 |
| L3 | p50 wall time per investigation | with changes ≤ 1.15 × without changes (the plan's latency budget) |

Reported without a threshold: category accuracy for each configuration with a 95% Wilson interval; diff citations accepted over generated; `corroborated` counts; p95 wall time. With 30 cases, accuracy differences of 3–4 cases are within noise.

### Dev results already seen (frozen dev splits; for reference, not thresholds)
- v3-change: comparability 1.000; Hit@1 0.789 (baselines 0.684, 0.421); MRR 0.895 (0.816, 0.675); Hit@3 1.000 (0.947, 0.947); no invalid status; 0 correlated suspects without a culprit.
- v3-history: precision 1.000, recall 0.943, Recall@5 1.000, 0 of 13 look-alikes merged.
- Model ablation (draft, 30 dev cases): correct 29 with changes and 28 without; 0 wrong `corroborated` in both; 0 `corroborated` on diff evidence alone; diff citations 11/12 valid; p50 36.6 s with changes and 43.0 s without.

### Regression guard (v2 **dev** split; not a held-out result)
`evaluate.py diagnosis --dataset v2 --split dev --configs "rules-only (M3 agent),agent + hybrid (M3)"`, compared with v1.0's last run (`m52-v2-dev.md`, commit `5f001dc`).

| id | metric | threshold |
|---|---|---|
| R1 | Wrong `corroborated` answers, each configuration | 0 |
| R2 | Correct answers | rules-only ≥ 52/60 (v1.0: 55); agent + hybrid ≥ 50/60 (v1.0: 53) |

## Order of runs
1. Freeze both sets, and commit them with this protocol and the frozen system.
2. Regression guard (R1, R2), for the record. The dev-split model ablation already ran once as a draft before the freeze (`v11-change-llm-dev-draft.md`: 30 dev cases, including the 2 later excluded and `d02` before its last rewrite).
3. Each test split once: v3-change deterministic, v3-history, then the v3-change model ablation.
4. Report every number as measured, including failed thresholds. No re-run of a test split, and no change to Kensa in response to its answers.

## Limits stated in advance
- **Synthetic data, one author:** results show how the methods behave on realistic, independently written cases, not their accuracy on real repositories. The validator is a separate task of the same model family as the author.
- **Development on dev:** fingerprint version 2 and the composer and docker-pull signature changes were developed on the v3-history dev split. The change-analysis ranking weights were fixed in M7.3 before any v3 case existed.
- **Labels:** history clusters and change culprits are the author's labels after validation. Where root causes are not separable from the log alone (for example one test failing for two reasons that differ only in values), the deterministic fingerprint is expected to miss; that limits recall, not precision.
- **Model ablation:** 30 cases per split, one run per configuration, a 4 GB laptop GPU. Model variation between runs is not measured.
