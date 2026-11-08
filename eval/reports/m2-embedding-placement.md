# M2 embedding placement

> Measured by `scripts/measure_embeddings.py`: the LLM is loaded first with the D-009 options, then 64 knowledge-base chunks are embedded in batches of 16.

- **Date (UTC):** 2026-10-29 23:33 · **Git:** 705afad
- **LLM:** qwen3:4b-instruct-2507-q4_K_M · **Embedding model:** qwen3-embedding:0.6b
- **GPU:** NVIDIA GeForce RTX 3050 Laptop GPU, 4096 MiB, 610.62 · VRAM used at start: 0 MiB

| placement | chunks/s (warm) | warm time s | first-call time s | peak VRAM MiB | embedder in VRAM/size MiB | LLM in VRAM/size MiB before → after |
|---|---|---|---|---|---|---|
| CPU (num_gpu=0) | 0.8 | 79.9 | 3.8 | 3695 | 0/1180 | 3612/3612 → 3612/3612 |
| Ollama default | 41.3 | 1.5 | 27.7 | 3695 | 1171/1171 | 3612/3612 → 0/0 |
