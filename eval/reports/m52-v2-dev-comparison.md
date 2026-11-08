# M5.1 comparison: v2 dev, M5.2 regression check

Metric definitions: `eval/reports/m51-protocol.md`. Statuses are compared across vocabularies: the strongest status is `verified` (M5) or `corroborated` (M5.1); a hedged status is `supported` or `plausible`; a conflict status is `contradicted` or `conflicting`.

| system | config | correct (95% CI) | incorrect | incorrect with the strongest status | incorrect, hedged | incorrect, flagged as conflicting | abstained correctly / missed | insufficient detected | strongest status correct | citations valid | wall p50 / p95 s | model call p50 / p95 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M5.1 (last dev run) | rules-only (M3 agent) | 55/60 (0.82-0.96) | 0 | 0 | 0 | 0 | 6 / 5 | 6/6 | 38/38 (100%) | 67/67 (100%) | 0.3 / 0.4 | — |
| M5.1 (last dev run) | llm + fts | 54/60 (0.80-0.95) | 3 | 0 | 3 | 0 | 4 / 3 | 4/6 | 31/31 (100%) | 211/224 (94%) | 15.4 / 18.2 | 15.3 / 18.1 |
| M5.1 (last dev run) | agent + fts (M3) | 54/60 (0.80-0.95) | 3 | 0 | 3 | 0 | 4 / 3 | 4/6 | 31/31 (100%) | 206/221 (93%) | 11.5 / 21.0 | 9.2 / 12.0 |
| M5.1 (last dev run) | agent + hybrid (M3) | 53/60 (0.78-0.94) | 3 | 0 | 3 | 0 | 4 / 4 | 4/6 | 28/28 (100%) | 203/217 (94%) | 26.1 / 34.5 | 16.2 / 19.0 |
| M5.2 (5f001dc) | rules-only (M3 agent) | 55/60 (0.82-0.96) | 0 | 0 | 0 | 0 | 6 / 5 | 6/6 | 33/33 (100%) | 67/67 (100%) | 0.5 / 0.7 | — |
| M5.2 (5f001dc) | llm + fts | 52/60 (0.76-0.93) | 5 | 0 | 3 | 2 | 4 / 3 | 4/6 | 27/27 (100%) | 211/225 (94%) | 17.4 / 22.4 | 17.2 / 22.2 |
| M5.2 (5f001dc) | agent + fts (M3) | 53/60 (0.78-0.94) | 4 | 0 | 3 | 1 | 4 / 3 | 4/6 | 28/28 (100%) | 201/217 (93%) | 10.5 / 23.0 | 8.8 / 10.7 |
| M5.2 (5f001dc) | agent + hybrid (M3) | 53/60 (0.78-0.94) | 3 | 0 | 3 | 0 | 4 / 4 | 4/6 | 24/24 (100%) | 203/217 (94%) | 30.9 / 40.6 | 17.8 / 23.5 |

## Accuracy by case kind

| system | config | standard | masked | misleading | lookalike | insufficient |
|---|---|---|---|---|---|---|
| M5.1 (last dev run) | rules-only (M3 agent) | 28/32 | 12/12 | 5/6 | 4/4 | 6/6 |
| M5.1 (last dev run) | llm + fts | 29/32 | 12/12 | 5/6 | 4/4 | 4/6 |
| M5.1 (last dev run) | agent + fts (M3) | 29/32 | 12/12 | 5/6 | 4/4 | 4/6 |
| M5.1 (last dev run) | agent + hybrid (M3) | 29/32 | 12/12 | 5/6 | 3/4 | 4/6 |
| M5.2 (5f001dc) | rules-only (M3 agent) | 28/32 | 12/12 | 5/6 | 4/4 | 6/6 |
| M5.2 (5f001dc) | llm + fts | 29/32 | 12/12 | 5/6 | 2/4 | 4/6 |
| M5.2 (5f001dc) | agent + fts (M3) | 29/32 | 12/12 | 5/6 | 3/4 | 4/6 |
| M5.2 (5f001dc) | agent + hybrid (M3) | 29/32 | 12/12 | 5/6 | 3/4 | 4/6 |
