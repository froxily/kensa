# M5.1 comparison: v2 dev split (60 cases; used for M5.1 development)

Metric definitions: `eval/reports/m51-protocol.md`. Statuses are compared across vocabularies: the strongest status is `verified` (M5) or `corroborated` (M5.1); a hedged status is `supported` or `plausible`; a conflict status is `contradicted` or `conflicting`.

| system | config | correct (95% CI) | incorrect | incorrect with the strongest status | incorrect, hedged | incorrect, flagged as conflicting | abstained correctly / missed | insufficient detected | strongest status correct | citations valid | wall p50 / p95 s | model call p50 / p95 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M5 (d7c6f56) | rules-only (M3 agent) | 34/60 (0.44-0.68) | 5 | 5 | 0 | 0 | 6 / 21 | 6/6 | 28/33 (85%) | 44/44 (100%) | 0.2 / 0.3 | — |
| M5 (d7c6f56) | llm + fts | 40/60 (0.54-0.77) | 9 | 1 | 8 | 0 | 4 / 11 | 4/6 | 18/19 (95%) | 217/240 (90%) | 15.1 / 18.1 | 15.0 / 17.9 |
| M5 (d7c6f56) | agent + fts (M3) | 41/60 (0.56-0.79) | 9 | 2 | 7 | 0 | 4 / 10 | 4/6 | 19/21 (90%) | 199/216 (92%) | 11.9 / 19.6 | 8.7 / 11.6 |
| M5 (d7c6f56) | agent + hybrid (M3) | 43/60 (0.59-0.81) | 11 | 3 | 8 | 0 | 4 / 6 | 4/6 | 21/24 (88%) | 211/226 (93%) | 24.0 / 36.1 | 15.6 / 18.4 |
| M5.1 | rules-only (M3 agent) | 55/60 (0.82-0.96) | 0 | 0 | 0 | 0 | 6 / 5 | 6/6 | 38/38 (100%) | 67/67 (100%) | 0.3 / 0.4 | — |
| M5.1 | llm + fts | 54/60 (0.80-0.95) | 3 | 0 | 3 | 0 | 4 / 3 | 4/6 | 31/31 (100%) | 211/224 (94%) | 15.4 / 18.2 | 15.3 / 18.1 |
| M5.1 | agent + fts (M3) | 54/60 (0.80-0.95) | 3 | 0 | 3 | 0 | 4 / 3 | 4/6 | 31/31 (100%) | 206/221 (93%) | 11.5 / 21.0 | 9.2 / 12.0 |
| M5.1 | agent + hybrid (M3) | 53/60 (0.78-0.94) | 3 | 0 | 3 | 0 | 4 / 4 | 4/6 | 28/28 (100%) | 203/217 (94%) | 26.1 / 34.5 | 16.2 / 19.0 |

## Accuracy by case kind

| system | config | standard | masked | misleading | lookalike | insufficient |
|---|---|---|---|---|---|---|
| M5 (d7c6f56) | rules-only (M3 agent) | 19/32 | 5/12 | 2/6 | 2/4 | 6/6 |
| M5 (d7c6f56) | llm + fts | 23/32 | 8/12 | 3/6 | 2/4 | 4/6 |
| M5 (d7c6f56) | agent + fts (M3) | 23/32 | 8/12 | 3/6 | 3/4 | 4/6 |
| M5 (d7c6f56) | agent + hybrid (M3) | 25/32 | 8/12 | 3/6 | 3/4 | 4/6 |
| M5.1 | rules-only (M3 agent) | 28/32 | 12/12 | 5/6 | 4/4 | 6/6 |
| M5.1 | llm + fts | 29/32 | 12/12 | 5/6 | 4/4 | 4/6 |
| M5.1 | agent + fts (M3) | 29/32 | 12/12 | 5/6 | 4/4 | 4/6 |
| M5.1 | agent + hybrid (M3) | 29/32 | 12/12 | 5/6 | 3/4 | 4/6 |
