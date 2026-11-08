"""Bundled sample incidents. Synthetic, hand-written logs, and labelled as such in the UI."""

from dataclasses import dataclass
from pathlib import Path

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "samples"


@dataclass(frozen=True)
class Sample:
    id: str
    title: str
    description: str
    filename: str

    def read(self) -> str:
        return (SAMPLE_DIR / self.filename).read_text(encoding="utf-8")


SAMPLES: tuple[Sample, ...] = (
    Sample(
        "missing-env-var",
        "Frontend build fails an environment check",
        "A Vite build stops in a pre-build script before compiling.",
        "missing-env-var.log",
    ),
    Sample(
        "dependency-resolution",
        "npm ci cannot resolve dependencies",
        "Dependency installation fails before any build step runs.",
        "dependency-resolution.log",
    ),
    Sample(
        "db-connection",
        "Test setup errors in a Python service",
        "pytest errors while setting up a test that needs a database.",
        "db-connection.log",
    ),
)
_BY_ID = {s.id: s for s in SAMPLES}


def get_sample(sample_id: str) -> Sample | None:
    return _BY_ID.get(sample_id)
