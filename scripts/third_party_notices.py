"""Write THIRD_PARTY_NOTICES.md from local metadata only (M6): no network, nothing installed.

    uv run --directory backend --no-sync python ../scripts/third_party_notices.py

- Python: the backend's runtime closure from uv.lock (``uv export --no-dev``), each licence read
  from the installed package's metadata.
- Frontend: the production dependency tree (``npm ls --omit=dev``), each licence from the
  package's own package.json, with the full licence text, since these packages are bundled into
  the built app.
  Packages that hold only type declarations (no JavaScript) never reach the bundle and are left
  out, by name.
- The replay build's own notices (``frontend/replay/THIRD_PARTY_NOTICES.txt``): Kensa's licence
  and the bundled frontend packages' texts, shipped next to the static build's index.html.
- Models: the licence text in the local Ollama manifest (``ollama show --license``), next to what
  the upstream model page states (``UPSTREAM``, checked by hand; this script reads no network).
A licence that the metadata does not state is reported as such, never guessed.
"""

import json
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from kensa.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "frontend"
OUTPUT = REPO_ROOT / "THIRD_PARTY_NOTICES.md"
# Served next to index.html by the replay build (frontend/replay is its public directory).
REPLAY_NOTICES = FRONTEND / "replay" / "THIRD_PARTY_NOTICES.txt"
UNSTATED = "not stated in the package metadata"
CODE = {".js", ".mjs", ".cjs"}
# What each model's publisher states, read by hand (Kensa never fetches these). Kensa does not
# distribute either model: users download them with Ollama.
UPSTREAM = {
    "qwen3:4b-instruct-2507-q4_K_M": (
        "Apache-2.0: the publisher's model card `Qwen/Qwen3-4B-Instruct-2507` (checked 2026-11-02)"
    ),
    "qwen3-embedding:0.6b": (
        "Apache-2.0: the Qwen Team's announcement (qwenlm.github.io/blog/qwen3-embedding,"
        " 2025-06-05) releases the series under the Apache 2.0 license on Hugging Face and"
        " ModelScope, and the publisher's model card `Qwen/Qwen3-Embedding-0.6B` declares"
        " apache-2.0 (checked 2026-11-03). Neither repository ships a LICENSE or NOTICE file"
    ),
}


def run(*argv: str) -> str:
    """Run a fixed local tool (argv built in this file) and return its output."""
    executable = shutil.which(argv[0])
    if executable is None:
        raise SystemExit(f"{argv[0]} is not on PATH")
    return subprocess.run(  # noqa: S603  (fixed argv built in this file)
        [executable, *argv[1:]], capture_output=True, text=True, check=True, encoding="utf-8"
    ).stdout


def python_licence(name: str) -> str:
    info = metadata.metadata(name)
    if expression := info.get("License-Expression"):
        return str(expression)
    classifiers = [
        c.removeprefix("License :: OSI Approved :: ").removeprefix("License :: ")
        for c in info.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    if classifiers:
        return "; ".join(classifiers)
    text = (info.get("License") or "").strip()
    return text.splitlines()[0][:80] if text else UNSTATED


def python_packages() -> list[tuple[str, str, str]]:
    exported = run(
        "uv", "export", "--directory", str(REPO_ROOT / "backend"), "--no-dev", "--no-hashes",
        "--frozen", "--format", "requirements-txt",
    )  # fmt: skip
    rows = []
    for line in exported.splitlines():
        requirement, _, marker = (part.strip() for part in line.partition(";"))
        if "==" not in requirement or requirement.startswith(("#", "-")):
            continue
        name, version = requirement.split("==", 1)
        try:
            licence = python_licence(name)
        except metadata.PackageNotFoundError:
            # Locked for another platform only; uv did not install it here.
            licence = f"not installed on this platform (`{marker}`)"
        rows.append((name, version, licence))
    return sorted(rows, key=lambda row: row[0].lower())


def has_code(folder: Path) -> bool:
    """Whether a package ships JavaScript (type-only packages hold just ``.d.ts`` files)."""
    return any(
        path.suffix in CODE and "node_modules" not in path.relative_to(folder).parts
        for path in folder.rglob("*")
    )


def npm_packages() -> tuple[list[tuple[str, str, str, str | None]], list[str]]:
    tree: dict[str, Any] = json.loads(
        run("npm", "--prefix", str(FRONTEND), "ls", "--omit=dev", "--all", "--json")
    )
    found: dict[str, str] = {}

    def walk(node: dict[str, Any]) -> None:
        for name, child in (node.get("dependencies") or {}).items():
            if name not in found:
                found[name] = child.get("version", "?")
                walk(child)

    walk(tree)
    rows, types_only = [], []
    for name, version in sorted(found.items()):
        folder = FRONTEND / "node_modules" / name
        if not has_code(folder):
            types_only.append(name)
            continue
        package = json.loads((folder / "package.json").read_text(encoding="utf-8"))
        licence = package.get("license")
        texts = [p for p in folder.iterdir() if p.name.lower().startswith(("license", "licence"))]
        text = texts[0].read_text(encoding="utf-8").strip() if texts else None
        rows.append((name, version, licence if isinstance(licence, str) else UNSTATED, text))
    return rows, types_only


def model_licence(model: str) -> str:
    lines = [line.strip() for line in run("ollama", "show", model, "--license").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return "not stated"
    return ", ".join(lines[:2])


def main() -> int:
    settings = Settings()
    python = python_packages()
    frontend, types_only = npm_packages()
    models = [(m, model_licence(m)) for m in (settings.llm_model, settings.embedding_model)]
    copyleft = [kind for kind in ("LGPL", "MPL") if any(kind in row[2] for row in python)]

    out = [
        "# Third-party notices",
        "",
        "Generated by `scripts/third_party_notices.py` from local metadata (uv.lock, installed",
        "packages, `node_modules`, the local Ollama manifests). Kensa's own code is under the MIT",
        "licence (`LICENSE`). Development tools (test runners, linters, the build toolchain) are",
        "not distributed and are not listed.",
        "",
        "## Python packages (backend runtime)",
        "",
        "Installed by `uv sync` from PyPI; none is copied into this repository.",
        *(
            [
                f"Packages under the {' or the '.join(copyleft)} are used unmodified, as separately"
                " installed libraries.",
            ]
            if copyleft
            else []
        ),
        "",
        "| Package | Version | Licence |",
        "|---|---|---|",
        *(f"| {name} | {version} | {licence} |" for name, version, licence in python),
        "",
        "## Frontend packages (bundled into the built app)",
        "",
        "| Package | Version | Licence |",
        "|---|---|---|",
        *(f"| {name} | {version} | {licence} |" for name, version, licence, _ in frontend),
        "",
        "Also in the production dependency tree, but holding only type declarations, so nothing of",
        f"them reaches the bundle: {', '.join(f'`{name}`' for name in types_only)}.",
        "",
        "## Models (downloaded by the user with Ollama; not distributed with Kensa)",
        "",
        "| Model | Local Ollama manifest | Upstream (checked by hand, 2026-11-02) |",
        "|---|---|---|",
        *(
            f"| `{model}` | {licence} | {UPSTREAM.get(model, 'not checked')} |"
            for model, licence in models
        ),
        "",
        "## Services (run by the user; not distributed with Kensa)",
        "",
        "- `pgvector/pgvector:0.8.7-pg18` (Docker image pulled by `docker compose`): PostgreSQL",
        "  and the pgvector extension, both under the PostgreSQL License (pgvector's own LICENSE",
        "  file, checked 2026-11-02).",
        "- Ollama, installed by the user from ollama.com: MIT License (its repository's LICENSE",
        "  file, checked 2026-11-02).",
        "",
        "## Licence texts of the bundled frontend packages",
    ]
    for name, version, _, text in frontend:
        out += ["", f"### {name} {version}", ""]
        out += ["```text", text, "```"] if text else ["No licence file in the package."]
    OUTPUT.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(
        f"Wrote {OUTPUT.name}: {len(python)} Python, {len(frontend)} frontend, {len(models)} models"
    )
    REPLAY_NOTICES.write_text(replay_notices(frontend, models), encoding="utf-8", newline="\n")
    print(f"Wrote {REPLAY_NOTICES.relative_to(REPO_ROOT)}")
    return 0


def replay_notices(
    frontend: list[tuple[str, str, str, str | None]], models: list[tuple[str, str]]
) -> str:
    """The notices that must travel with the static replay build, which bundles the frontend
    packages and shows recorded model output (copied into dist-replay as a static file)."""
    out = [
        "Kensa replay demo: licence and third-party notices",
        "=" * 50,
        "",
        "This static build contains Kensa's own code and data, under the MIT licence below,",
        "and the frontend packages listed after it, bundled into its JavaScript.",
        "",
        "The recorded diagnoses were produced by a local model that is not part of this build:",
        *(f"  {model}: {UPSTREAM.get(model, licence)}" for model, licence in models[:1]),
        "",
        "-" * 50,
        "Kensa",
        "-" * 50,
        (REPO_ROOT / "LICENSE").read_text(encoding="utf-8").strip(),
    ]
    for name, version, licence, text in frontend:
        out += ["", "-" * 50, f"{name} {version} ({licence})", "-" * 50]
        out.append(text if text else "No licence file in the package.")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.exit(main())
