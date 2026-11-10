# v1.1.0 evaluation protocol: historical failure intelligence (fixed before the v4 held-out split runs)

Written and committed before the `v4-history` test split runs for the first time. Nothing below may change after that run. The test split runs once. If a threshold is missed, the result is reported as measured, and historical matching is not released as a confirmed feature (see "Decision rule").

## Why a new set
Fingerprint version 2 met every threshold on the v3-history dev split and missed three on its held-out split (precision 0.682, recall 0.469, 4 of 13 look-alikes merged; `v11-results.md`). That split is spent. Version 3 (D-057) is measured on a fresh set, `eval/datasets/v4-history`, written for a much wider range of tools and ecosystems.

## Data
- **Authorship:** a separate LLM author, isolated from Kensa's code, wrote every sequence from the committed spec and plan (`AUTHORING_SPEC.md`, `plan.csv`, commit `1f944a6`). The test sequences (`ht31`–`ht60`) were never opened by the engineer who builds Kensa; gate messages, verdict words and disputed field names were seen.
- **Quality gates** (`scripts/freeze_v3.py --dataset v4-history`), then an **independent validator pass** (a separate task, blind labelling, then comparison) on a seeded 20% of each split (`random.Random(20261110)`) plus every sequence rewritten after a gate finding, with one revision round and one re-validation; items still disputed or still failing a gate are moved to `excluded/` (`AUTHORING.md`).
- **Sizes and digests:** filled in at the freeze, before the test run (see the final section).

## System
- Kensa at the commit recorded in the report, with fingerprint version 3 (`kensa.analysis.fingerprint`), committed before the test run. No rule, family, subject pattern, mask or threshold changes between the last dev measurement and the test run.
- Deterministic: no model. Every log is investigated in order (rules-only provider), as in production.

## Development record (dev data only; stated in advance)
- Version 3 was designed on the v3-history dev split, then checked **once** on the unseen v4-history dev sequences then written (26 sequences): precision 0.842, recall 0.432, 2 of 17 look-alikes merged. That is the honest generalization estimate of the first design.
- General fixes were then made from v4-history dev (summaries, headers, test names across runners, decoration, numbered names). Final dev results: v3-history dev precision 1.000 / recall 0.943 / 0 of 13 look-alikes merged; v4-history dev 1.000 / 0.651 / 0 of 22 (29 sequences). On the frozen dev split (28 sequences, after the validation excluded `hd53`): precision 1.000, recall 0.667, Recall@5 0.946, 0 of 21 look-alikes merged, 0 of 28 "same failure" labels wrong (`v11-v4-history-dev.md`). Dev numbers are not held-out results.

## Metrics and thresholds (`evaluate_v3.py --dataset v4-history --split test --allow-test-split`)
A **recurrence claim** is two investigations sharing an *exact* primary fingerprint of version 3. Approximate fingerprints never claim a recurrence.

| id | metric | threshold (the owner's original targets) |
|---|---|---|
| F1 | Pairwise **precision** of recurrence claims (claimed pairs in the same cluster / all claimed pairs) | ≥ 0.90 |
| F2 | Pairwise **recall** (same-cluster pairs that are claimed / all same-cluster pairs) | ≥ 0.60 |
| F3 | **Look-alikes merged:** look-alike entries whose exact fingerprint equals an earlier entry of another cluster | ≤ 10% of look-alikes |
| F4 | Similar-failure **Recall@5:** for each recurrence, an earlier entry of its cluster is among the 5 similar failures shown | ≥ 0.90 |
| F5 | **"Same failure" labels shown in the History panel** that point to another cluster | ≤ 10% of such labels |

Reported without a threshold: the share of exact and approximate fingerprints, entries without an exact fingerprint, and a breakdown by rule family (metadata only).

## Decision rule (stated in advance)
- **All of F1–F5 met:** historical failure intelligence ships in v1.1.0 as a feature, with the separation between exact recurrences and approximate similarity.
- **Any of F1–F5 missed:** the result is reported as measured; historical matching is marked **experimental** and is off by default in the release candidate, and the release stops before publication for the owner's decision.

## Limits stated in advance
- Synthetic sequences from one separate LLM author; validated by a separate task of the same model family.
- 30 sequences per split before exclusions; pairwise metrics on such counts move by several points with a few pairs.
- Failures whose causes differ only in values, or that name nothing specific, are designed to stay approximate; that limits recall, not precision.

## Final sizes and digests
After the gates, the validation and its revision round (`eval/datasets/v4-history/AUTHORING.md`):

| Split | Sequences | Entries | Excluded | Manifest digest |
|---|---|---|---|---|
| dev | 28 | 112 | `hd52` (gate), `hd53` (validation) | `97ae4220b9235f48` |
| test | 28 | 112 | `ht51`, `ht56` (validation) | `0d6fc6d5afa7fbcd` |
| whole set | 56 | 224 | | `b142406ab0c6a11f` |

The digests are those printed by `freeze_v3.py` (dev, test, `--all`). The frozen set, this protocol and the system under test are committed together before the test split runs.
