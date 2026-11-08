# M5.1 comparison: v2 dev, M5.1 development run 2

Metric definitions: `eval/reports/m51-protocol.md`. Statuses are compared across vocabularies: the strongest status is `verified` (M5) or `corroborated` (M5.1); a hedged status is `supported` or `plausible`; a conflict status is `contradicted` or `conflicting`.

| system | config | correct (95% CI) | incorrect | incorrect with the strongest status | incorrect, hedged | incorrect, flagged as conflicting | abstained correctly / missed | insufficient detected | strongest status correct | citations valid | wall p50 / p95 s | model call p50 / p95 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M5.1 dev run 2 | rules-only (M3 agent) | 55/60 (0.82-0.96) | 0 | 0 | 0 | 0 | 6 / 5 | 6/6 | 38/38 (100%) | 67/67 (100%) | 0.3 / 0.4 | — |
| M5.1 dev run 2 | llm + fts | 54/60 (0.80-0.95) | 3 | 0 | 3 | 0 | 4 / 3 | 4/6 | 31/31 (100%) | 211/224 (94%) | 15.4 / 18.2 | 15.3 / 18.1 |
| M5.1 dev run 2 | agent + fts (M3) | 54/60 (0.80-0.95) | 3 | 0 | 3 | 0 | 4 / 3 | 4/6 | 31/31 (100%) | 206/221 (93%) | 11.5 / 21.0 | 9.2 / 12.0 |
| M5.1 dev run 2 | agent + hybrid (M3) | 53/60 (0.78-0.94) | 3 | 0 | 3 | 0 | 4 / 4 | 4/6 | 28/28 (100%) | 203/217 (94%) | 26.1 / 34.5 | 16.2 / 19.0 |

## Accuracy by case kind

| system | config | standard | masked | misleading | lookalike | insufficient |
|---|---|---|---|---|---|---|
| M5.1 dev run 2 | rules-only (M3 agent) | 28/32 | 12/12 | 5/6 | 4/4 | 6/6 |
| M5.1 dev run 2 | llm + fts | 29/32 | 12/12 | 5/6 | 4/4 | 4/6 |
| M5.1 dev run 2 | agent + fts (M3) | 29/32 | 12/12 | 5/6 | 4/4 | 4/6 |
| M5.1 dev run 2 | agent + hybrid (M3) | 29/32 | 12/12 | 5/6 | 3/4 | 4/6 |
