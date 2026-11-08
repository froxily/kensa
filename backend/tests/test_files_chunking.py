import pytest

from kensa.ingestion.files import chunk_file, source_type_for

WORKFLOW = """name: ci
on:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      API_URL: http://localhost
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npm test
  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - run: ./deploy.sh
""".splitlines()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".github/workflows/ci.yml", "workflow_yaml"),
        (".github\\workflows\\release.yaml", "workflow_yaml"),
        ("docs/README.md", "doc"),
        ("src/app.py", "code"),
        ("Dockerfile", "code"),
        ("config/workflows/x.yml", "code"),
    ],
)
def test_source_type_for(path: str, expected: str) -> None:
    assert source_type_for(path) == expected


def test_workflow_is_chunked_by_job_with_exact_lines() -> None:
    chunks = chunk_file(".github/workflows/ci.yml", WORKFLOW)
    by_label = {c.step_name: c for c in chunks}
    assert by_label["workflow settings"].start_line == 1
    assert by_label["workflow settings"].end_line == 6
    test_job = by_label["job test"]
    assert (test_job.start_line, test_job.end_line) == (8, 15)
    assert test_job.content.splitlines()[0] == "  test:"
    assert "npm test" in test_job.content
    deploy = by_label["job deploy"]
    assert (deploy.start_line, deploy.end_line) == (16, 20)
    for chunk in chunks:  # content always equals the cited line range
        assert chunk.content == "\n".join(WORKFLOW[chunk.start_line - 1 : chunk.end_line])


def test_long_jobs_are_split_into_steps() -> None:
    steps = [f"      - name: step {i}\n        run: echo {i}" for i in range(40)]
    text = "on: push\njobs:\n  big:\n    runs-on: ubuntu-latest\n    steps:\n" + "\n".join(steps)
    lines = text.splitlines()
    chunks = chunk_file(".github/workflows/big.yml", lines)
    step_chunks = [c for c in chunks if c.kind == "step"]
    assert len(step_chunks) == 40
    assert step_chunks[0].content.strip().startswith("- name: step 0")
    assert step_chunks[-1].end_line == len(lines)


def test_invalid_yaml_falls_back_to_windows() -> None:
    chunks = chunk_file(".github/workflows/bad.yml", ["jobs: [", "  - oops: {"])
    assert chunks
    assert chunks[0].kind == "workflow"


def test_markdown_sections_follow_headings_outside_code_fences() -> None:
    lines = ["# Title", "intro", "## Setup", "```", "# not a heading", "```", "## Usage", "run it"]
    chunks = chunk_file("README.md", lines)
    assert [(c.step_name, c.start_line, c.end_line) for c in chunks] == [
        ("Title", 1, 2),
        ("Setup", 3, 6),
        ("Usage", 7, 8),
    ]


def test_python_is_chunked_by_top_level_definition() -> None:
    lines = [
        "import os",
        "",
        "def load():",
        "    return os.environ['X']",
        "",
        "class Svc:",
        "    pass",
    ]
    chunks = chunk_file("app/settings.py", lines)
    assert [(c.start_line, c.end_line) for c in chunks] == [(1, 1), (3, 4), (6, 7)]
    assert chunks[1].step_name == "def load():"


def test_unknown_files_use_windows_and_skip_blank_chunks() -> None:
    lines = [f"key{i}=value" for i in range(130)]
    chunks = chunk_file("settings.properties", lines)
    assert [(c.start_line, c.end_line) for c in chunks] == [(1, 60), (61, 120), (121, 130)]
    assert chunk_file("empty.txt", ["", "  "]) == []
