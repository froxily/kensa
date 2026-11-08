# M0 primary-model benchmark

> Measured on this machine by `scripts/benchmark_model.py`. The fixtures are synthetic (`eval/fixtures/m0-benchmark`), so this is a **resource and output-format smoke test, not an accuracy evaluation**. Raw per-run data: `eval/reports/m0-model-benchmark-numgpu99.jsonl`.

## Environment

- **Date (UTC):** 2026-10-29 22:06
- **Git:** 60ca5c9
- **Model:** qwen3:4b-instruct-2507-q4_K_M (digest 0edcdef34593)
- **Ollama:** 0.40.13
- **GPU:** NVIDIA GeForce RTX 3050 Laptop GPU, 4096 MiB, 610.62
- **OS / Python:** Windows-11-10.0.26200-SP0 / 3.13.5
- **Options:** {"temperature": 0, "seed": 42, "num_predict": 512, "num_gpu": 99}, format = JSON schema, sequential requests

## Results by context size

| num_ctx | fully on GPU | model size (MiB) | in VRAM (MiB) | VRAM before / peak (MiB) | Ollama RAM (MiB) | median tok/s | median / max latency (s) | schema-valid | category match | errors |
|---|---|---|---|---|---|---|---|---|---|---|
| 4096 | yes | 3032 | 3032 | 0 / 3125 | 168 | 51.6 | 1.9 / 5.1 | 5/5 | 2/5 | 0 |
| 6144 | yes | 3322 | 3322 | 0 / 3415 | 168 | 50.5 | 1.9 / 5.5 | 5/5 | 2/5 | 0 |
| 8192 | yes | 3612 | 3612 | 0 / 3705 | 168 | 49.4 | 2.0 / 5.9 | 5/5 | 2/5 | 0 |
| 12288 | yes | 4192 | 4192 | 0 / 3901 | 121 | 42.5 | 3.6 / 8.1 | 5/5 | 2/5 | 0 |

## Notes

- Stopped at num_ctx=12288: peak VRAM 3901 MiB is within 128 MiB of the 3962 MiB usable (likely shared-memory spill).
- Latency includes model load on the first run of each step (`load_s` in raw data).
- Category match on 5 synthetic logs is a sanity check only.
