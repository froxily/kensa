# Evaluation dataset v2: authoring specification

This set measures whether a CI-failure diagnosis tool names the **underlying cause** of a failed GitHub Actions job, not just its visible symptom, and whether it says so when the evidence cannot establish a cause. You are the **independent author**: you write every case and its ground truth. The people building the tool write none of the content and assign no labels.

## Isolation (strict)
- **You may read and write only inside `eval/datasets/v2/`:** this specification, `plan.csv`, and the cases you write under `eval/datasets/v2/cases/`.
- **Do not open, list or search anything else in the repository:** `backend/`, `frontend/`, `scripts/`, `knowledge/`, `eval/datasets/v1/`, `eval/reports/`, `eval/fixtures/`, `.github/`, and every root-level document. They describe the tool under test, and reading them would make the set non-independent.
- **Do not run project code, tests or package managers, and do not use the network.**
- **Write every case by hand.** No generator scripts, templates or loops that produce case content. You may use shell commands only to create directories and write files.

## Ground truth: the category is what must change to fix the failure
Choose exactly one category per case using this rule, even when the visible symptom belongs to another category.

| category | the fix is to… |
|---|---|
| `missing_env_var` | supply an environment variable or secret that is absent or empty (including a secret that is configured but empty for that event) |
| `github_permissions` | grant the workflow token or a credential a missing permission or scope (403, "denied", "not accessible", a package write refused) |
| `db_connectivity` | fix how the job reaches or authenticates to a database or cache service: service not started, port not published, wrong host, port or database name, wrong credentials **value** (when the variable is present but wrong) |
| `docker` | fix the Docker daemon, an image reference or pull, a registry problem that is not a permission, or the Dockerfile's own build logic (base image, stage, copy context) |
| `workflow_path` | correct a file, directory, working directory or action path that the workflow or its tooling references and that does not exist |
| `dependency_build` | fix dependency resolution, installation, a lockfile, toolchain or language version, or a compile or type error in the build |
| `test_regression` | change code or a test expectation: the tests ran in a correctly configured environment and an assertion failed |
| `oom_timeout` | give the job more memory, disk or time, or reduce what it uses (killed, exit 137, heap exhausted, disk full, timed out, cancelled for time) |
| `unknown` | nothing: the evidence available in the log and repository files cannot establish the cause |

Tie-breakers:
- **A missing variable** that leads to a failed database login is `missing_env_var`; a present but wrong value is `db_connectivity`.
- **A registry push refused** because the token lacks package write permission is `github_permissions`, not `docker`.
- **A test that fails only because** a variable, permission, service, path, dependency or resource is missing has the category of that missing thing, **not** `test_regression`.

## Case kinds (fixed per case by `plan.csv`)
- **standard:** the failing output shows the cause in its own category's terms.
- **masked:** the job's final failure is reported by a different tool than the cause, for example a failing test, a failed Docker build or push step, or a script exiting non-zero (the `note` column says which). The underlying cause is still visible somewhere in the log, as real tools would print it: an error message inside a test's output, a warning a few lines earlier, a stack trace, a service log line. The repository files may confirm it. A careful reader can find the cause; a reader who only looks at the final summary lines gets the symptom.
- **misleading:** a prominent error points at the wrong category, for example a loud secondary error, a deprecation warning, a retry message or a later cascade failure. The true cause is earlier or quieter in the log, or only clear with a repository file.
- **lookalike:** the cause really is the labelled category, but the output contains wording typical of another category. For example, a test that asserts on an error message mentioning a missing variable, while the actual regression is a code change, or a database-backed test that reaches the database fine but gets the wrong rows. The environment is correctly configured.
- **insufficient** (category `unknown`; the `note` says which): the log does not establish the cause.
  - **generic exit:** only a generic failure such as "exit code 1" with output suppressed.
  - **truncated log:** the log is cut off before the failing command's output, and says so.
  - **two equally plausible causes:** the evidence fits two different categories equally well and nothing available distinguishes them.
  - The `root_cause` field explains why the cause cannot be established.

## Realism requirements
- **`log.txt`:** 50–140 lines of a GitHub Actions job log.
  - Every line has an ISO timestamp prefix like real job logs (`2026-09-14T08:12:03.4512345Z `), including the runner set-up, the checkout, the steps' own commands, and `##[group]`/`##[endgroup]`/`##[error]` markers where GitHub prints them.
  - Tool output must look like what that tool really prints: compilers, test runners, package managers, Docker/BuildKit, database clients, shells. Include ordinary noise: progress lines, warnings, timing lines, secondary errors.
  - **Never** add commentary that names or explains the root cause in words a tool would not print. No "root cause:", no "NOTE:", no "hint".
  - **Never** include text addressed to an AI or a reviewer.
- **`repo/`:** 3–6 files, including exactly the workflow that ran, under `repo/.github/workflows/`.
  - The other files are what the failure involves: source files, tests, configuration, a Dockerfile, a lockfile excerpt, a compose file.
  - Names, step names, commands, paths and line numbers in stack traces must match between the log and the files.
- **Secrets:** never write anything that looks like a real credential (no `ghp_…`, `github_pat_…`, `AKIA…`, private keys, real passwords). GitHub masks secret values as `***`. Use obviously fake values only where a tool would print them.
- **Variety:** use different organisation, repository, service, variable, test and file names in every case, never the same ones twice. Use the suggested ecosystem from `plan.csv` unless it makes the case unrealistic, in which case choose another and record it. Vary log length, step structure and runner image.
- **Difficulty:** `easy`, `medium` or `hard`, your judgement.

## `case.json` (exact format)
```json
{
  "id": "d07-<short-slug>",
  "split": "dev",
  "category": "missing_env_var",
  "kind": "masked",
  "difficulty": "medium",
  "ecosystem": "go",
  "title": "A short title",
  "root_cause": "Two to four sentences: what is wrong and why the job failed, as an expert would explain it.",
  "fix_keywords": ["1 to 4 exact tokens a correct fix would mention, e.g. a variable or file name"],
  "relevant_evidence": [
    {"path": "log", "start_line": 61, "end_line": 63, "why": "What these lines show."},
    {"path": ".github/workflows/ci.yml", "start_line": 18, "end_line": 22, "why": "What these lines show."}
  ]
}
```
- **Plan fields:** `id` starts with the plan's `id_prefix` followed by `-` and a short slug, and the folder name equals the `id`. `split`, `category` and `kind` must equal the plan row.
- **Evidence:** `relevant_evidence` lists 1–4 ranges, with line numbers exact and 1-based. `path` is `log` or a path relative to `repo/`. At least one range is in the log. For masked and misleading cases, include the line(s) that reveal the true cause.

## Batches and self-review
- **Batches:** write the cases in the order of `plan.csv`, in the batch you are given. Finish every file of a case before starting the next.
- **Self-review:** after each batch, review your own cases against this specification: realism, label rule, exact line numbers, no giveaway commentary, no reuse of names. Fix problems before reporting.
- **Labels:** do not change a plan row's category or kind. If a planned case cannot be written realistically, say so in your report instead.
- **Report:** at the end of each batch, list the case ids written and anything you could not do.
