# M5.1 comparison: v2 dev, M5.1 development run 1

Metric definitions: `eval/reports/m51-protocol.md`. Statuses are compared across vocabularies: the strongest status is `verified` (M5) or `corroborated` (M5.1); a hedged status is `supported` or `plausible`; a conflict status is `contradicted` or `conflicting`.

| system | config | correct (95% CI) | incorrect | incorrect with the strongest status | incorrect, hedged | incorrect, flagged as conflicting | abstained correctly / missed | insufficient detected | strongest status correct | citations valid | wall p50 / p95 s | model call p50 / p95 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M5.1 rules | rules-only (M3 agent) | 55/60 (0.82-0.96) | 0 | 0 | 0 | 0 | 6 / 5 | 6/6 | 38/38 (100%) | 67/67 (100%) | 0.2 / 0.3 | — |
| M5.1 llm | llm + fts | 49/60 (0.70-0.89) | 5 | 0 | 3 | 2 | 4 / 6 | 4/6 | 26/26 (100%) | 222/237 (94%) | 15.2 / 18.7 | 15.0 / 18.6 |
| M5.1 llm | agent + fts (M3) | 49/60 (0.70-0.89) | 5 | 0 | 3 | 2 | 4 / 6 | 4/6 | 26/26 (100%) | 211/227 (93%) | 10.7 / 20.2 | 9.0 / 11.5 |
| M5.1 llm | agent + hybrid (M3) | 49/60 (0.70-0.89) | 4 | 0 | 3 | 1 | 4 / 7 | 4/6 | 24/24 (100%) | 211/227 (93%) | 24.6 / 35.0 | 15.9 / 19.0 |

## Accuracy by case kind

| system | config | standard | masked | misleading | lookalike | insufficient |
|---|---|---|---|---|---|---|
| M5.1 rules | rules-only (M3 agent) | 28/32 | 12/12 | 5/6 | 4/4 | 6/6 |
| M5.1 llm | llm + fts | 26/32 | 11/12 | 5/6 | 3/4 | 4/6 |
| M5.1 llm | agent + fts (M3) | 26/32 | 11/12 | 5/6 | 3/4 | 4/6 |
| M5.1 llm | agent + hybrid (M3) | 26/32 | 11/12 | 5/6 | 3/4 | 4/6 |
