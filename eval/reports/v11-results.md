# v1.1 results: change-aware investigation and failure history

> 2026-11-09. Kensa at `b81b375` (the commit that holds the frozen sets and the protocol; no Kensa code changed after it before these runs). Thresholds were fixed in [`v11-protocol.md`](v11-protocol.md) before any test split ran. Each held-out split was run **once**. Generated reports and raw rows: `v11-change-test.md`, `v11-history-test.md`, `v11-change-llm-test.md`, `v11-v2-dev-guard.md`, with matching `.jsonl` files.

## Summary
- **Change-aware investigation passes every pre-registered threshold on unseen cases.** Kensa's top suspect was the culprit in 81% of the held-out culprit cases, against 48% for "the largest diff" and 24% for "the most recent change", and every comparability verdict was right (30/30).
- **Fingerprints fail their pre-registered thresholds on unseen sequences.** Pairwise precision was 0.682 (threshold 0.90) and recall 0.469 (floor 0.60), against 1.000 and 0.943 on dev; 4 of 13 look-alikes were merged with an earlier failure (threshold 10%). Similar-failure Recall@5 met its threshold (0.96). **Fingerprint version 2 overfitted the dev split.**
- **Change evidence in the prompt did no harm, and changed no correct answer.** With and without the change analysis, the production agent was right on the same 26 of 30 held-out cases (95% Wilson 0.70–0.95), with no wrong `corroborated` answer and no `corroborated` answer resting on a diff. It also brought no measurable accuracy gain on these 30 cases.
- **No regression on v2 dev:** rules-only 56/60 (v1.0: 55), agent + hybrid 53/60 (v1.0: 53), no wrong `corroborated` answer in either.

## Thresholds (protocol) and results
| id | metric | threshold | held-out result | |
|---|---|---|---|---|
| C1 | culprit Hit@1 (21 culprit cases) | above both baselines | **0.810** (largest diff 0.476, most recent 0.238) | met |
| C2 | culprit MRR | above both baselines | **0.905** (0.706, 0.571) | met |
| C3 | comparability accuracy (30 cases) | ≥ 0.90 | **1.000** | met |
| C4 | every suspect `correlated` or `weak` | 100% | 100% | met |
| C5 | correlated suspects in the 9 cases without a culprit | 0 | 0 | met |
| H1 | fingerprint pairwise precision (72 entries) | ≥ 0.90 | **0.682** | **not met** |
| H2 | pairwise recall | ≥ 0.60 | **0.469** | **not met** |
| H3 | similar-failure Recall@5 (25 recurrences) | ≥ 0.90 | **0.960** | met |
| H4 | look-alikes merged with another cluster | ≤ 10% | **4 of 13 (31%)** | **not met** |
| L1 | wrong `corroborated`, with changes against without | with ≤ without | 0 and 0 | met |
| L2 | `corroborated` answers resting only on diff citations | 0 | 0 | met |
| L3 | p50 wall time, with changes against without | ≤ 1.15 × | 39.7 s and 46.4 s | met |
| R1 | wrong `corroborated`, v2 dev | 0 | 0 and 0 | met |
| R2 | correct answers, v2 dev | rules-only ≥ 52, agent + hybrid ≥ 50 | 56 and 53 | met |

Reported without a threshold: Hit@3 1.000 (both baselines 0.952), unverified-factor exact match 1.000.

## Dev against held-out
| | dev (frozen) | held-out |
|---|---|---|
| culprit Hit@1 / MRR | 0.789 / 0.895 | 0.810 / 0.905 |
| comparability | 1.000 | 1.000 |
| fingerprint precision / recall | 1.000 / 0.943 | **0.682 / 0.469** |
| Recall@5 | 1.000 | 0.960 |
| look-alikes merged | 0 of 13 | **4 of 13** |

The change analysis transferred: its baseline choice, factors and ranking weights were fixed in M7.3, before any v3 case existed. The fingerprint did not: version 2 was developed on the dev split (D-053), and the held-out run shows that its rules fitted dev's tools and wording.

## Why the fingerprints failed (post hoc, by metadata only)
After the run, the primary fingerprint of each held-out entry was recomputed and grouped by the rule that produced it, without reading any log text, subject or template. This is for reporting; nothing was changed in response.
- **The generic fallback carried more of the load:** the tool's last error line (`generic.failure`) was the primary for 16 of 72 held-out entries, against 8 of 76 on dev. The held-out logs used tools and wordings the signature rules do not know.
- **False merges (7 pairs):** mostly primaries without a subject, where two different causes masked to the same line (`generic.failure`, a dependency-resolution and a compile line), and two entries with the same empty variable but different causes.
- **Missed recurrences (17 pairs):** either the same rule produced different templates (a summary or a module line worded differently between runs), or recurrences of one failure picked **different primary rules** (for example a module-import rule in one run and a missing-module rule in the next).
- **What would fix it is not known from this data.** The v3-history test split is now spent, so any next fingerprint version has to be measured on new data, such as the planned lab repository's real runs or a new independent set.

## What did not change
- **Similar failures are history, not evidence** (D-051, D-053): wrong fingerprints can put a wrong earlier failure in the History panel, but never into the evidence or the prompt, and never change a status. The deterministic test that a wrong earlier diagnosis cannot change a later one passes.
- **Recall@5 met its threshold**, because similar-failure search falls back to related fingerprints and wording: an earlier occurrence of the same failure was among the five shown for 24 of 25 recurrences.

## The model ablation in detail (held out, 30 cases, one run each)
| | with changes | without changes |
|---|---|---|
| correct category | 26/30 (0.70–0.95) | 26/30 (0.70–0.95) |
| `corroborated` | 11, all right | 11, all right |
| valid citations | 102/110 | 99/111 |
| diff citations valid | 9/11 | (none offered) |
| p50 / p95 wall time | 39.7 s / 55.9 s | 46.4 s / 71.6 s |

- **The same category on 29 of 30 cases**, and the same 4 wrong cases (`t04`, `t08`, `t16`, `t24`); `t08` was wrong both ways (`not_established` with changes, a test regression without). Six right answers changed status between `corroborated` and `plausible`, three each way, which is consistent with run-to-run variation.
- **Latency:** each case ran both configurations back to back, so both saw the same GPU state. The GPU was hot and throttled throughout (`v11-gpu-samples.csv`, 94 samples every 30 s: median 88 °C, median SM clock 776 MHz, minimum 307 MHz, median power 29.8 W). The lower time with changes is not explained and not claimed as a gain.
- **Dev (draft, before the freeze):** 29/30 with changes and 28/30 without, also with no wrong `corroborated` answer.

## Regression guard (v2 dev; not a held-out result)
- rules-only: 56/60 (v1.0: 55). The one change is `d43` (a Composer failure), now classified by the new `composer.unresolvable` signature.
- agent + hybrid: 53/60 (v1.0: 53), with the same category and status as v1.0 on every case.
- Wrong `corroborated`: 0 in both.
- LLM p50: 25.7 s, against 17.8 s for v1.0's run. The GPU state was not sampled during this run; during the evening's earlier model runs it was at 88 °C with a reduced clock, so throttling is the likely cause, not established.

## Limits
- Synthetic sets from one separate LLM author, validated by a separate task of the same model family. 30 change cases and 18 history sequences per held-out split.
- One model run per configuration on a 4 GB laptop GPU; model variation between runs is not measured.
