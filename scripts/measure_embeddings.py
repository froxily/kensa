"""M2: where should the embedding model run while the LLM occupies the GPU?

Loads the LLM with the D-009 options (as during a diagnosis), then embeds the knowledge-base
chunks twice: on the CPU (num_gpu=0) and with Ollama's default placement. Records throughput,
peak VRAM, and whether the LLM stayed fully in VRAM. Writes
eval/reports/m2-embedding-placement.md. Never downloads models.

    uv run --directory backend --no-sync python ../scripts/measure_embeddings.py
"""

import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from benchmark_model import VramSampler, git_sha, gpu_description, unload, vram_used_mib

from kensa.core.config import Settings
from kensa.inference.ollama import normalize_model_name

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "eval" / "reports" / "m2-embedding-placement.md"


def texts() -> list[str]:
    chunks: list[str] = []
    for path in sorted((REPO_ROOT / "knowledge").rglob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        chunks += ["\n".join(lines[i : i + 12]) for i in range(0, len(lines), 12)]
    return (chunks * 4)[:64]


def placement(client: httpx.Client) -> dict[str, tuple[int, int]]:
    return {
        normalize_model_name(str(m["name"])): (
            int(m["size"]) // 2**20,
            int(m["size_vram"]) // 2**20,
        )
        for m in client.get("/api/ps").json().get("models", [])
    }


def load_llm(client: httpx.Client, settings: Settings) -> None:
    options = {"num_ctx": settings.llm_num_ctx, "num_gpu": settings.llm_num_gpu, "num_predict": 1}
    payload = {
        "model": settings.llm_model,
        "prompt": "ok",
        "stream": False,
        "options": options,
        "keep_alive": "10m",
    }
    client.post("/api/generate", json=payload, timeout=180)


def embed(client: httpx.Client, model: str, inputs: list[str], options: dict[str, Any]) -> float:
    started = time.perf_counter()
    for start in range(0, len(inputs), 16):
        body = {
            "model": model,
            "input": inputs[start : start + 16],
            "options": options,
            "keep_alive": "10m",
            "truncate": True,
        }
        client.post("/api/embed", json=body, timeout=300).raise_for_status()
    return time.perf_counter() - started


def main() -> int:
    settings = Settings()
    llm, emb = (
        normalize_model_name(settings.llm_model),
        normalize_model_name(settings.embedding_model),
    )
    inputs = texts()
    rows: list[str] = []
    with httpx.Client(base_url=settings.ollama_base_url) as client:
        for label, options in (("CPU (num_gpu=0)", {"num_gpu": 0}), ("Ollama default", {})):
            unload(client, settings.embedding_model)
            unload(client, settings.llm_model)
            time.sleep(2)
            load_llm(client, settings)
            before = placement(client)
            with VramSampler() as sampler:
                cold = embed(client, settings.embedding_model, inputs[:1], options)
                warm = embed(client, settings.embedding_model, inputs, options)
            after = placement(client)
            llm_after = after.get(llm, (0, 0))
            emb_after = after.get(emb, (0, 0))
            rows.append(
                f"| {label} | {len(inputs) / warm:.1f} | {warm:.1f} | {cold:.1f} "
                f"| {sampler.peak_mib} | {emb_after[1]}/{emb_after[0]} "
                f"| {before.get(llm, (0, 0))[1]}/{before.get(llm, (0, 0))[0]} "
                f"→ {llm_after[1]}/{llm_after[0]} |"
            )
            print(rows[-1], flush=True)
        unload(client, settings.embedding_model)
    lines = [
        "# M2 embedding placement",
        "",
        "> Measured by `scripts/measure_embeddings.py`: the LLM is loaded first with the D-009 "
        f"options, then {len(inputs)} knowledge-base chunks are embedded in batches of 16.",
        "",
        f"- **Date (UTC):** {datetime.now(UTC):%Y-%m-%d %H:%M} · **Git:** {git_sha()}",
        f"- **LLM:** {settings.llm_model} · **Embedding model:** {settings.embedding_model}",
        f"- **GPU:** {gpu_description()} · VRAM used at start: {vram_used_mib()} MiB",
        "",
        "| placement | chunks/s (warm) | warm time s | first-call time s | peak VRAM MiB "
        "| embedder in VRAM/size MiB | LLM in VRAM/size MiB before → after |",
        "|---|---|---|---|---|---|---|",
        *rows,
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
