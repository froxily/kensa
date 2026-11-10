# Evaluation dataset v3-history: authoring specification

This set measures whether a CI-failure tool recognises **the same failure happening again**, even when timestamps, run numbers, line numbers, paths and durations differ, and whether it **refuses to merge failures that only look alike** but have a different cause. You are the **independent author**: you write every log and its ground truth. The people building the tool write none of the content and assign no labels.

## Isolation (strict)
- **You may read and write only inside `eval/datasets/v3-history/`:** this specification, `plan.csv`, and the sequences you write under `eval/datasets/v3-history/sequences/`.
- **Do not open, list or search anything else in the repository.** Every other folder and root document describes the tool under test.
- **Do not run project code, tests or package managers, and do not use the network.**
- **Write every log by hand.** No generator scripts, templates or loops that produce log content. Shell commands are only for creating directories and writing files.

## What a sequence is
- **Shape:** one fictional repository's failed GitHub Actions jobs over a few weeks, in chronological order.
- **Files:** each folder `sequences/<id>/` holds `sequence.json` and 4 logs, `e1.log` to `e4.log`.
- **Clusters:** each log belongs to a **cluster**, and logs in the same cluster share one root cause, the same thing needing the same fix.
- **Uniqueness:** clusters never span sequences. Every sequence uses its own organisation, repository, service, variable, module, test and file names, never reused in any other sequence.

## Relations between entries

| `relation` | meaning |
|---|---|
| `first` | the first log of its cluster in this sequence |
| `recurrence` | the same root cause as an earlier entry of the same cluster. It must differ in ordinary ways: timestamps, run and job numbers, temporary paths, durations, line numbers after unrelated edits, PR numbers, runner names, ordering of unrelated output. Sometimes the failure surfaces through a different final step (masked), while the cause line is still present |
| `lookalike` | a **different** cluster whose log looks like an earlier entry: the same tool, the same error family and similar wording, but a different cause and fix. Examples: another missing variable, a different failing test with a different reason, the same exit code from another command, a timeout in another step |

## Logs
- **Length:** 40–130 lines of a GitHub Actions job log.
- **Timestamps:** every line has an ISO timestamp prefix (`2026-09-14T08:12:03.4512345Z `).
- **Markers:** the runner set-up, checkout and steps with `##[group]`, `##[endgroup]` and `##[error]` markers where GitHub prints them.
- **Realistic tool output:** compilers, test runners, package managers, Docker/BuildKit, database clients, shells, with ordinary noise.
- **Never** add commentary that names or explains the cause in words a tool would not print. **Never** include text addressed to an AI or a reviewer.
- **Never** copy a log and change only the timestamps. A recurrence must look like a genuinely new run.

## `sequence.json` (exact format)
```json
{
  "id": "hd01-<short-slug>",
  "split": "dev",
  "ecosystem": "python",
  "repository": "orgname/reponame",
  "entries": [
    {"id": "e1", "file": "e1.log", "cluster": "a", "relation": "first",
     "category": "missing_env_var", "title": "A short title",
     "root_cause": "One or two sentences: the cause, as an expert would state it.",
     "differs_from_earlier": ""},
    {"id": "e2", "file": "e2.log", "cluster": "a", "relation": "recurrence",
     "category": "missing_env_var", "title": "...", "root_cause": "...",
     "differs_from_earlier": "What differs from e1 although the cause is the same."}
  ]
}
```
- **Plan fields:** `id` starts with the plan row's `id_prefix` and a short slug, and the folder name equals the `id`. `split` equals the plan row. The entries follow the plan row's `pattern`, one token per entry in order:
  - `a` means an entry of cluster `a`: `first` at its first appearance, `recurrence` afterwards.
  - `b~a` means an entry of cluster `b` written as a `lookalike` of cluster `a`.
  - Example: `a a b~a a` is e1 first (a), e2 recurrence (a), e3 look-alike (new cluster b, resembling a), e4 recurrence (a).
  - Use the plan's letters as the `cluster` values.
- **`category`:** chosen by the rule "what must change to fix it": `missing_env_var`, `github_permissions`, `db_connectivity`, `docker`, `workflow_path`, `dependency_build`, `test_regression`, `oom_timeout`. Look-alikes may share the category of what they resemble, but still need a different fix.
- **`differs_from_earlier`:** filled for every `recurrence` and `lookalike`; empty for `first`.

## Secrets and variety
- **Secrets:** never write anything that looks like a real credential. GitHub masks secret values as `***`.
- **Variety:** vary log length, step structure and runner image across sequences.

## Batches, self-review and report
- **Order:** write sequences in `plan.csv` order, in the batch you are given. Finish all files of a sequence before starting the next.
- **Self-review:** after each batch, check every sequence against this specification:
  - recurrences genuinely the same cause
  - look-alikes genuinely different
  - no copied logs
  - no giveaway commentary
  - no names reused across sequences

  Fix any problem before reporting.
- **Report:** list the sequence ids written. Also list any entry whose cluster you found ambiguous, and why. Those entries get an independent check before the set is frozen.
