# M5 evaluation: held-out test split (and dev under the same frozen system)

Metric definitions: `eval/reports/m5-protocol.md` (fixed before the test run). Raw rows: `m5-diagnosis-test.jsonl`, `m5-diagnosis-dev.jsonl`. "Grounded but wrong" is checked in the database for the test split (an accepted citation from the run's own log); for dev, whose runs are no longer stored, it is inferred from the status (verified, supported and contradicted all require an accepted log citation).

## Held-out test split (20 cases, first and only run)

| config | correct | incorrect | abstained: correctly / missed | insufficient detected | false confidence | grounded but wrong (of which verified) | citations valid (final; all attempts) | wall p50 / p95 s | model call p50 / p95 s |
|---|---|---|---|---|---|---|---|---|---|
| rules-only (M3 agent) | 11/20 | 4 | 2 / 5 | 2/2 | 4 | 4 (4) | 18/18 (100%); 18/18 | 0.3 / 0.5 | — |
| llm, no retrieval (log tail) | 12/20 | 7 | 1 / 1 | 1/2 | 6 | 7 (4) | 77/80 (96%); 77/80 | 14.4 / 20.5 | 14.3 / 20.3 |
| llm + fts | 13/20 | 5 | 1 / 2 | 1/2 | 4 | 5 (2) | 74/80 (92%); 74/80 | 10.2 / 12.3 | 10.1 / 12.2 |
| llm + hybrid (M2) | 13/20 | 5 | 2 / 2 | 2/2 | 4 | 5 (2) | 79/80 (99%); 79/80 | 21.3 / 24.0 | 16.2 / 16.9 |
| agent + fts (M3) | 12/20 | 6 | 1 / 2 | 1/2 | 6 | 6 (3) | 73/78 (94%); 92/98 | 16.9 / 27.4 | 9.4 / 12.4 |
| agent + hybrid (M3) | 12/20 | 6 | 2 / 2 | 2/2 | 6 | 6 (3) | 79/80 (99%); 91/92 | 23.6 / 39.9 | 15.4 / 17.3 |

| config | standard | misleading | insufficient |
|---|---|---|---|
| rules-only (M3 agent) | 8/16 | 1/2 | 2/2 |
| llm, no retrieval (log tail) | 10/16 | 1/2 | 1/2 |
| llm + fts | 11/16 | 1/2 | 1/2 |
| llm + hybrid (M2) | 10/16 | 1/2 | 2/2 |
| agent + fts (M3) | 10/16 | 1/2 | 1/2 |
| agent + hybrid (M3) | 9/16 | 1/2 | 2/2 |

## Dev split, same frozen system

| config | correct | incorrect | abstained: correctly / missed | insufficient detected | false confidence | grounded but wrong (of which verified) | citations valid (final; all attempts) | wall p50 / p95 s | model call p50 / p95 s |
|---|---|---|---|---|---|---|---|---|---|
| rules-only (M3 agent) | 15/20 | 0 | 2 / 5 | 2/2 | 0 | 0 (0) | 17/17 (100%); 17/17 | 0.3 / 0.5 | — |
| llm, no retrieval (log tail) | 14/20 | 2 | 1 / 4 | 1/2 | 2 | 2 (0) | 72/77 (94%); 72/77 | 20.7 / 28.1 | 20.5 / 27.9 |
| llm + fts | 15/20 | 2 | 1 / 3 | 1/2 | 2 | 2 (0) | 72/80 (90%); 72/80 | 15.7 / 23.4 | 15.4 / 23.2 |
| llm + hybrid (M2) | 18/20 | 2 | 1 / 0 | 1/2 | 2 | 2 (0) | 74/80 (92%); 74/80 | 29.3 / 35.3 | 23.4 / 28.6 |
| agent + fts (M3) | 16/20 | 1 | 2 / 3 | 2/2 | 1 | 1 (0) | 59/65 (91%); 70/77 | 20.7 / 38.3 | 15.1 / 23.3 |
| agent + hybrid (M3) | 20/20 | 0 | 2 / 0 | 2/2 | 0 | 0 (0) | 65/72 (90%); 65/72 | 32.0 / 58.3 | 22.4 / 29.9 |

| config | standard | misleading | insufficient |
|---|---|---|---|
| rules-only (M3 agent) | 11/16 | 2/2 | 2/2 |
| llm, no retrieval (log tail) | 12/16 | 1/2 | 1/2 |
| llm + fts | 13/16 | 1/2 | 1/2 |
| llm + hybrid (M2) | 15/16 | 2/2 | 1/2 |
| agent + fts (M3) | 13/16 | 1/2 | 2/2 |
| agent + hybrid (M3) | 16/16 | 2/2 | 2/2 |

## Checks on the test run

- Independent re-check of every accepted citation in the test run: 400 accepted, 0 not found on their cited line.
- Incorrect diagnoses with confidence ≥ 0.5 (test): 29

## Test cases answered incorrectly or missed, per configuration

| case | kind | expected | config | predicted | status | confidence |
|---|---|---|---|---|---|---|
| c03-spring-audit-sink | standard | missing_env_var | rules-only (M3 agent) | unknown | unknown | 0.00 |
| c03-spring-audit-sink | standard | missing_env_var | llm, no retrieval (log tail) | test_regression | supported | 0.70 |
| c03-spring-audit-sink | standard | missing_env_var | llm + fts | test_regression | supported | 0.70 |
| c03-spring-audit-sink | standard | missing_env_var | llm + hybrid (M2) | test_regression | supported | 0.70 |
| c03-spring-audit-sink | standard | missing_env_var | agent + fts (M3) | test_regression | supported | 0.70 |
| c03-spring-audit-sink | standard | missing_env_var | agent + hybrid (M3) | test_regression | supported | 0.70 |
| c04-go-region | standard | missing_env_var | rules-only (M3 agent) | test_regression | verified | 0.90 |
| c04-go-region | standard | missing_env_var | llm, no retrieval (log tail) | test_regression | verified | 0.98 |
| c04-go-region | standard | missing_env_var | llm + fts | test_regression | verified | 0.98 |
| c04-go-region | standard | missing_env_var | llm + hybrid (M2) | test_regression | verified | 0.98 |
| c04-go-region | standard | missing_env_var | agent + fts (M3) | test_regression | verified | 0.98 |
| c04-go-region | standard | missing_env_var | agent + hybrid (M3) | test_regression | verified | 0.98 |
| c08-cargo-msrv | standard | dependency_build | rules-only (M3 agent) | unknown | unknown | 0.00 |
| c10-postgres-user-env | misleading | missing_env_var | rules-only (M3 agent) | test_regression | verified | 0.40 |
| c10-postgres-user-env | misleading | missing_env_var | llm, no retrieval (log tail) | test_regression | verified | 0.95 |
| c10-postgres-user-env | misleading | missing_env_var | llm + fts | test_regression | contradicted | 0.40 |
| c10-postgres-user-env | misleading | missing_env_var | llm + hybrid (M2) | test_regression | contradicted | 0.40 |
| c10-postgres-user-env | misleading | missing_env_var | agent + fts (M3) | db_connectivity | supported | 0.70 |
| c10-postgres-user-env | misleading | missing_env_var | agent + hybrid (M3) | db_connectivity | supported | 0.70 |
| c13-ghcr-package-write | standard | github_permissions | rules-only (M3 agent) | docker | verified | 0.90 |
| c13-ghcr-package-write | standard | github_permissions | llm, no retrieval (log tail) | docker | verified | 0.98 |
| c13-ghcr-package-write | standard | github_permissions | llm + fts | docker | verified | 0.98 |
| c13-ghcr-package-write | standard | github_permissions | llm + hybrid (M2) | docker | verified | 0.95 |
| c13-ghcr-package-write | standard | github_permissions | agent + fts (M3) | docker | verified | 0.98 |
| c13-ghcr-package-write | standard | github_permissions | agent + hybrid (M3) | docker | verified | 0.95 |
| c18-redis-unpublished-port | standard | db_connectivity | rules-only (M3 agent) | test_regression | verified | 0.80 |
| c18-redis-unpublished-port | standard | db_connectivity | llm, no retrieval (log tail) | test_regression | verified | 0.98 |
| c18-redis-unpublished-port | standard | db_connectivity | agent + fts (M3) | test_regression | verified | 0.95 |
| c18-redis-unpublished-port | standard | db_connectivity | agent + hybrid (M3) | test_regression | verified | 0.95 |
| c24-docker-stage-compile | standard | docker | llm, no retrieval (log tail) | test_regression | contradicted | 0.40 |
| c24-docker-stage-compile | standard | docker | llm + fts | unknown | unknown | 0.20 |
| c24-docker-stage-compile | standard | docker | llm + hybrid (M2) | unknown | unknown | 0.20 |
| c24-docker-stage-compile | standard | docker | agent + fts (M3) | unknown | unknown | 0.20 |
| c24-docker-stage-compile | standard | docker | agent + hybrid (M3) | unknown | unknown | 0.20 |
| c27-dotnet-solution-path | standard | workflow_path | rules-only (M3 agent) | unknown | unknown | 0.00 |
| c27-dotnet-solution-path | standard | workflow_path | llm, no retrieval (log tail) | unknown | unknown | 0.20 |
| c27-dotnet-solution-path | standard | workflow_path | llm + fts | unknown | unknown | 0.20 |
| c27-dotnet-solution-path | standard | workflow_path | llm + hybrid (M2) | dependency_build | supported | 0.70 |
| c27-dotnet-solution-path | standard | workflow_path | agent + fts (M3) | unknown | unknown | 0.20 |
| c27-dotnet-solution-path | standard | workflow_path | agent + hybrid (M3) | dependency_build | supported | 0.70 |
| c28-composite-action-path | standard | workflow_path | rules-only (M3 agent) | unknown | unknown | 0.00 |
| c37-gradle-heap | standard | oom_timeout | rules-only (M3 agent) | unknown | unknown | 0.00 |
| c37-gradle-heap | standard | oom_timeout | llm + hybrid (M2) | unknown | unknown | 0.20 |
| c37-gradle-heap | standard | oom_timeout | agent + hybrid (M3) | unknown | unknown | 0.20 |
| c40-ambiguous-service | insufficient | unknown | llm, no retrieval (log tail) | test_regression | supported | 0.70 |
| c40-ambiguous-service | insufficient | unknown | llm + fts | test_regression | supported | 0.70 |
| c40-ambiguous-service | insufficient | unknown | agent + fts (M3) | test_regression | supported | 0.70 |
