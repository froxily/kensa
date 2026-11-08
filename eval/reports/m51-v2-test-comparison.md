# M5.1 comparison: v2 held-out test split (60 cases, first completed run)

Metric definitions: `eval/reports/m51-protocol.md`. Statuses are compared across vocabularies: the strongest status is `verified` (M5) or `corroborated` (M5.1); a hedged status is `supported` or `plausible`; a conflict status is `contradicted` or `conflicting`.

| system | config | correct (95% CI) | incorrect | incorrect with the strongest status | incorrect, hedged | incorrect, flagged as conflicting | abstained correctly / missed | insufficient detected | strongest status correct | citations valid | wall p50 / p95 s | model call p50 / p95 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M5 (d7c6f56) | rules-only (M3 agent) | 28/60 (0.35-0.59) | 1 | 1 | 0 | 0 | 6 / 31 | 6/6 | 22/23 (96%) | 35/35 (100%) | 0.3 / 0.5 | — |
| M5 (d7c6f56) | llm + fts | 38/60 (0.51-0.74) | 10 | 0 | 8 | 2 | 5 / 12 | 5/6 | 13/13 (100%) | 217/240 (90%) | 14.6 / 17.6 | 14.5 / 17.5 |
| M5 (d7c6f56) | agent + fts (M3) | 39/60 (0.52-0.76) | 9 | 0 | 8 | 1 | 5 / 12 | 5/6 | 14/14 (100%) | 190/209 (91%) | 12.4 / 19.9 | 8.1 / 10.3 |
| M5 (d7c6f56) | agent + hybrid (M3) | 41/60 (0.56-0.79) | 9 | 0 | 8 | 1 | 5 / 10 | 5/6 | 13/13 (100%) | 215/227 (95%) | 21.8 / 33.6 | 14.7 / 18.2 |
| M5.1 | rules-only (M3 agent) | 41/60 (0.56-0.79) | 3 | 3 | 0 | 0 | 5 / 16 | 5/6 | 23/26 (88%) | 56/56 (100%) | 0.2 / 0.3 | — |
| M5.1 | llm + fts | 44/60 (0.61-0.83) | 3 | 2 | 1 | 0 | 5 / 13 | 5/6 | 16/18 (89%) | 195/222 (88%) | 13.6 / 18.0 | 13.5 / 17.9 |
| M5.1 | agent + fts (M3) | 44/60 (0.61-0.83) | 3 | 2 | 1 | 0 | 5 / 13 | 5/6 | 17/19 (89%) | 191/213 (90%) | 9.7 / 19.0 | 8.2 / 11.0 |
| M5.1 | agent + hybrid (M3) | 44/60 (0.61-0.83) | 8 | 2 | 5 | 1 | 5 / 8 | 5/6 | 18/20 (90%) | 204/220 (93%) | 20.3 / 31.0 | 14.5 / 18.5 |

## Accuracy by case kind

| system | config | standard | masked | misleading | lookalike | insufficient |
|---|---|---|---|---|---|---|
| M5 (d7c6f56) | rules-only (M3 agent) | 16/32 | 4/12 | 2/6 | 0/4 | 6/6 |
| M5 (d7c6f56) | llm + fts | 21/32 | 5/12 | 4/6 | 3/4 | 5/6 |
| M5 (d7c6f56) | agent + fts (M3) | 21/32 | 6/12 | 4/6 | 3/4 | 5/6 |
| M5 (d7c6f56) | agent + hybrid (M3) | 22/32 | 8/12 | 4/6 | 2/4 | 5/6 |
| M5.1 | rules-only (M3 agent) | 22/32 | 7/12 | 4/6 | 3/4 | 5/6 |
| M5.1 | llm + fts | 25/32 | 7/12 | 4/6 | 3/4 | 5/6 |
| M5.1 | agent + fts (M3) | 25/32 | 7/12 | 4/6 | 3/4 | 5/6 |
| M5.1 | agent + hybrid (M3) | 24/32 | 8/12 | 4/6 | 3/4 | 5/6 |
