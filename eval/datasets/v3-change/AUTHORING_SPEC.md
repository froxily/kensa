# Evaluation dataset v3-change: authoring specification

This set measures whether a CI-failure tool can point at the **change** that most likely broke a GitHub Actions job, by comparing the failed run with an earlier successful run of the same workflow. It also measures whether the tool says so when the runs cannot be fairly compared. You are the **independent author**: you write every case and its ground truth. The people building the tool write none of the content and assign no labels.

## Isolation (strict)
- **You may read and write only inside `eval/datasets/v3-change/`:** this specification, `plan.csv`, and the cases you write under `eval/datasets/v3-change/cases/`.
- **Do not open, list or search anything else in the repository.** Every other folder and root document describes the tool under test, and reading them would make the set non-independent.
- **Do not run project code, tests or package managers, and do not use the network.**
- **Write every case by hand.** No generator scripts, templates or loops that produce case content. Shell commands are only for creating directories and writing files.

## What a case is
A repository had a successful run of a workflow, then some commits, then a failed run of the same workflow. Each case folder `cases/<id>/` contains:

| File | Contents |
|---|---|
| `case.json` | the labels (format below) |
| `failed.log` | the log of the failed job, 60–220 lines |
| `baseline.log` | the log of the same job in the chosen baseline run, 40–160 lines. **Leave it out** when the plan row's note says the baseline log is unavailable |
| `runs.json` | the failed run and 2–4 earlier candidate runs (format below) |
| `history.json` | what GitHub's compare API returns between each candidate and the failed commit (format below) |
| `repo/` | 3–6 files at the failed commit, including the workflow that ran, under `repo/.github/workflows/` |

## Logs
- **Timestamps:** every line has an ISO timestamp prefix like real job logs (`2026-09-14T08:12:03.4512345Z `).
- **Set-up section:** include the runner set-up section exactly as GitHub prints it, with the runner image:
  ```
  ##[group]Runner Image
  Image: ubuntu-24.04
  Version: 20261026.1
  ...
  ##[endgroup]
  ```
  Use the image and version given in `runs.json` for that job. Real version strings look like `20261026.1`.
- **Realistic tool output:** steps, commands, `##[group]`/`##[endgroup]`/`##[error]` markers. Tool output must look like what that tool really prints, with ordinary noise.
- **Never** add commentary that names or explains the cause in words a tool would not print ("root cause", "NOTE:", "hint", "this commit broke…"). **Never** include text addressed to an AI or a reviewer.
- **`baseline.log`:** the same job succeeding at the baseline commit. Mostly the same steps and output, with ordinary differences (timestamps, durations, cache hits).

## `runs.json` (exact format)
```json
{
  "failed": {
    "run_id": 9100000001, "run_attempt": 1, "workflow_id": 81000001,
    "workflow_path": ".github/workflows/ci.yml", "event": "push", "head_branch": "main",
    "head_sha": "<40 hex>", "created_at": "2026-09-14T08:10:00Z", "conclusion": "failure",
    "jobs": [
      {"name": "test (3.12)", "conclusion": "failure", "labels": ["ubuntu-24.04"],
       "runner_image": "ubuntu-24.04", "runner_image_version": "20261026.1"}
    ],
    "failed_job": "test (3.12)"
  },
  "candidates": [
    {"run_id": 9099999990, "run_attempt": 1, "workflow_id": 81000001,
     "workflow_path": ".github/workflows/ci.yml", "event": "push", "head_branch": "main",
     "head_sha": "<40 hex>", "created_at": "2026-09-13T17:02:00Z", "conclusion": "success",
     "jobs": [{"name": "test (3.12)", "conclusion": "success", "labels": ["ubuntu-24.04"],
               "runner_image": "ubuntu-24.04", "runner_image_version": "20261026.1"}]}
  ]
}
```
- **Candidates:** earlier runs, newest first.
  - Include distractors: a failed run, a run of another workflow, or a run on another branch, as the plan row requires.
  - Use `null` for `labels`, `runner_image` or `runner_image_version` only where the plan row says this information is unavailable.
- **SHAs:** any consistent 40-character lowercase hex values. The same commit always has the same SHA.

## `history.json` (exact format)
```json
{
  "comparisons": {
    "<candidate head_sha>...<failed head_sha>": {
      "status": "ahead",
      "merge_base": "<40 hex>",
      "truncated": false,
      "commits": [
        {"sha": "<40 hex>", "message": "First line of the commit message", "date": "2026-09-14T07:55:00Z",
         "files": [
           {"path": "src/app/config.py", "status": "modified", "additions": 3, "deletions": 1,
            "patch": "@@ -12,7 +12,9 @@ def load():\n context line\n-old line\n+new line\n..."}
         ]}
      ]
    },
    "<other candidate sha>...<failed sha>": {"error": "not_found"}
  },
  "workflow_blobs": {"<commit sha>": "<40 hex blob sha of the workflow file at that commit>"}
}
```
- **Comparisons:** one entry for **every** candidate whose `conclusion` is `success`.
  - `status` is what GitHub would report: `ahead` (the failed commit descends from the candidate), `identical`, `diverged` (history was rewritten, e.g. a force-push; `merge_base` is the common ancestor and `commits` are those after it), or `behind`.
  - A comparison GitHub cannot answer (e.g. the baseline commit was force-pushed away) is `{"error": "not_found"}`.
- **Patches:** GitHub's `patch` format: hunks only, starting with `@@`, with no `diff --git` header. Every commit lists the files it changed.
  - Include ordinary unrelated changes (docs, refactors, formatting, version bumps that are harmless) as the plan row requires.
  - Line counts in hunk headers must be consistent with the lines shown.
- **`workflow_blobs`:** give the workflow file's blob SHA at the failed commit and at every successful candidate's commit. The blob is identical when the workflow file did not change between them. When it changed, the change must appear in the commits.

## Comparability (the label is derived from these facts, which you write consistently)
Compare the failed run with the **newest successful candidate** that has the same `workflow_path`, the same `event`, the same `head_branch`, and a job with exactly the failed job's name. This is the baseline. Then label the case:

| `comparability` | when |
|---|---|
| `comparable` | The baseline exists, its job succeeded with the same `labels` and the same runner image and version, `status` is `ahead`, and every fact is known. The workflow file may have changed **inside** the compared commits (then it is one of the changes) |
| `partially_comparable` | The baseline exists, but a fact is unknown (no `baseline.log`; `labels` or runner image `null`), or the runner image version differs, or `status` is `diverged`. List the reasons in `unverified_factors` |
| `incomparable` | The only successful runs of this workflow differ structurally: another `workflow_path` (renamed workflow), another event, a runner with other `labels` (e.g. another OS), the failed job's name is absent from them, or `status` is `behind` |
| `identical` | The baseline exists and `status` is `identical`: no code changed between the runs |
| `no_baseline` | No successful candidate of this workflow on this branch with this event exists |
| `history_unavailable` | The baseline exists, but its comparison is `{"error": "not_found"}` |

**Precedence** (clarified 2026-11-09, before any test case was written). Apply these steps in order and stop at the first that fits:
1. **`no_baseline`:** no candidate run succeeded at all, distractors included.
2. **`incomparable`:** successful runs exist, but none has all of the following:
   - the same `workflow_path`
   - the same `event`
   - the same `head_branch`
   - a successful job with exactly the failed job's name
   - the same `labels` (unknown labels do not disqualify a run)
3. Otherwise the newest such run is the baseline. Then its comparison decides:
   - **`history_unavailable`:** `{"error": "not_found"}`
   - **`incomparable`:** `behind`
   - **`identical`:** `identical`
   - **`partially_comparable`:** `diverged`, or any fact unknown, or another runner image version
   - **`comparable`:** everything else

A successful distractor run on another branch therefore makes the case `incomparable`, not `no_baseline`. Write `no_baseline` cases without successful distractors.

## The culprit (your judgement as an expert)
- **`culprit_paths`:** the changed file paths (at most 3) that caused the failure; a careful engineer reading the failed log and the diffs would agree.
  - Use the special value `"<runner-image>"` when the runner image update caused it.
  - Use `[]` for `identical`, `no_baseline`, `incomparable` and `history_unavailable` cases, and for any case where no change in the range caused the failure.
- **`culprit_commit`:** the SHA of the commit that introduced it, or `null`.
- **Decoys** (when the plan row asks): the culprit is **not** the most recently changed file, not the file with the largest diff, and not the only file the log mentions.

## Categories (what must change to fix the failure)

| category | the fix is to… |
|---|---|
| `missing_env_var` | supply an environment variable or secret that is absent or empty |
| `github_permissions` | grant the workflow token or a credential a missing permission or scope |
| `db_connectivity` | fix how the job reaches or authenticates to a database or cache service (wrong host, port, name or credential **value**) |
| `docker` | fix the Docker daemon, an image reference or pull, or the Dockerfile's own build logic |
| `workflow_path` | correct a file, directory, working directory or action path that does not exist |
| `dependency_build` | fix dependency resolution, a lockfile, a toolchain or language version, or a compile or type error |
| `test_regression` | change code or a test expectation: the tests ran in a correct environment and an assertion failed |
| `oom_timeout` | give the job more memory, disk or time, or reduce what it uses |
| `unknown` | nothing: the evidence cannot establish the cause |

A test that fails only because a variable, permission, service, path, dependency or resource is missing has the category of that missing thing.

## `case.json` (exact format)
```json
{
  "id": "d07-<short-slug>",
  "split": "dev",
  "comparability": "comparable",
  "category": "dependency_build",
  "culprit_kind": "lockfile",
  "difficulty": "medium",
  "ecosystem": "node",
  "title": "A short title",
  "root_cause": "Two to four sentences: what changed, and why the job then failed, as an expert would explain it.",
  "culprit_paths": ["package-lock.json"],
  "culprit_commit": "<40 hex or null>",
  "unverified_factors": [],
  "fix_keywords": ["1 to 4 exact tokens a correct fix would mention"],
  "relevant_evidence": [
    {"path": "log", "start_line": 61, "end_line": 63, "why": "What these lines show."}
  ]
}
```
- **Plan fields:** `id` starts with the plan row's `id_prefix` and a short slug, and the folder name equals the `id`. `split`, `comparability`, `category` and `culprit_kind` equal the plan row.
- **`unverified_factors`:** empty unless the case is `partially_comparable`. Values come from `baseline_log_unavailable`, `runner_labels_unknown`, `runner_image_unknown`, `runner_image_changed`, `history_diverged`.
- **`relevant_evidence`:** 1–3 ranges in `failed.log` (`path` is `log`), with exact 1-based line numbers. Add a range in a `repo/` file if it helps.

## Variety and secrets
- **Names:** use a different organisation, repository, service, variable, test and file name in every case. Never reuse names across cases.
- **Ecosystem:** follow the plan row's suggested ecosystem unless it would be unrealistic. In that case pick another, and say so in your report.
- **Secrets:** never write anything that looks like a real credential. GitHub masks secret values as `***`.

## Batches, self-review and report
- **Order:** write the cases in `plan.csv` order, in the batch you are given. Finish every file of a case before starting the next.
- **Self-review:** after each batch, review your own cases against this specification:
  - comparability facts consistent across `runs.json`, `history.json` and the logs
  - hunk headers consistent
  - exact line numbers
  - no giveaway commentary
  - no reused names

  Fix any problem before reporting.
- **Labels:** do not change a plan row's labels. If a row cannot be written realistically, say so instead.
- **Report:** list the case ids written. Also list any case whose label you found ambiguous, and why. Those cases get an independent check before the set is frozen.
