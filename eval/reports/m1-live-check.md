# M1 live check (local Ollama)

> Real investigations through the worker and the local model on this machine. Three inputs are the bundled synthetic samples and one is a long synthetic log built to fill the evidence budget. A functional and resource check, **not an accuracy evaluation**. Raw data: `eval/reports/m1-live-check.jsonl`.

- **Date (UTC):** 2026-10-29 22:58 · **Git:** 673da48
- **Model:** qwen3:4b-instruct-2507-q4_K_M · num_ctx 8192 · num_gpu 99
- **GPU:** NVIDIA GeForce RTX 3050 Laptop GPU, 4096 MiB, 610.62 · VRAM used before: 8 MiB
- **OS / Python:** Windows-11-10.0.26200-SP0 / 3.13.5

| case | status | rule hint | model category | verification | valid citations | confidence | prompt tok | output tok | LLM ms | peak VRAM MiB | model in VRAM/size MiB |
|---|---|---|---|---|---|---|---|---|---|---|---|
| missing-env-var | completed | missing_env_var | missing_env_var | verified | 4/4 | 1.0 | 749 | 308 | 10602 | 3699 | 3612/3612 |
| dependency-resolution | completed | dependency_build | dependency_build | verified | 4/4 | 1.0 | 914 | 335 | 8209 | 3699 | 3612/3612 |
| db-connection | completed | db_connectivity | db_connectivity | verified | 4/4 | 0.99 | 806 | 374 | 9060 | 3699 | 3612/3612 |
| long-pytest-log | completed | test_regression | test_regression | verified | 4/4 | 0.98 | 5062 | 340 | 12479 | 3699 | 3612/3612 |

## Model summaries (verbatim)

- **missing-env-var:** Missing required environment variable VITE_API_BASE_URL
- **dependency-resolution:** Peer dependency conflict between react versions in package.json
- **db-connection:** Database connection refused due to PostgreSQL server not running or not accepting connections on 127.0.0.1:5432
- **long-pytest-log:** Test assertions fail due to API returning totals one more than expected values
