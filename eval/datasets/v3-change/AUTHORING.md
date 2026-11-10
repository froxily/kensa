# Evaluation dataset v3-change: authoring record

## Authorship and independence
- **Author:** a separate LLM author wrote every case and every label: logs, run lists, histories with patches, repository files and `case.json`. Each case was written by a fresh, isolated task.
- **The engineer who builds Kensa** wrote the specification (`AUTHORING_SPEC.md`), the per-case plan (`plan.csv`: split, comparability, category, culprit kind, event, and a note per id) and the quality gates (`scripts/freeze_v3.py`). They wrote no case content and assigned no labels beyond the plan's columns.
- **Isolation:** each author task was told to read only `AUTHORING_SPEC.md`, `plan.csv` and the existing cases (to avoid reusing names, and for test rows to stay clearly different from dev cases). It ran no project code and used no network.
- **Held-out split:** the test cases (`t01`–`t30`) were never opened by the engineer. Gate messages, verdict words and disputed field names were seen; see "Exposure" for the rest.

## Distribution (per split; `plan.csv`)
| comparability | cases | culprit |
|---|---|---|
| `comparable` | 14 | a workflow, source, build-config, lockfile, manifest or test change |
| `partially_comparable` | 7 | as above, or the runner image; each names its unverified factors |
| `identical` | 3 | none (no code change) |
| `incomparable` | 3 | none |
| `no_baseline` | 2 | none |
| `history_unavailable` | 1 | none |

Categories cover all 8 non-`unknown` categories. Most culprit cases include decoys: larger, more recent or unrelated changes.

## Quality gates (`scripts/freeze_v3.py --dataset v3-change`)
- **Loading and shape:** every case loads; `failed.log` 60–220 lines, `baseline.log` 40–160 lines unless the plan says it is unavailable; 3–6 repository files including the workflow; evidence ranges inside the cited file.
- **Plan conformity:** id, split, comparability, category and culprit kind equal the plan row; culprit paths are among the changed files.
- **The comparability precedence**, checked independently from `runs.json` and `history.json` (`expected_comparability`), must give the labelled comparability.
- **Encoding:** every file is UTF-8.
- **No leaks:** no credential-like strings; no giveaway commentary.
- **Anti-template check:** no two logs share 3 or more of their distinctive lines above a set share. Standard runner, checkout, setup-action, service-container and Maven summary lines are excluded by an **explicit list**, never by corpus frequency.

## Fixes made by the engineer (mechanical, no content judgement)
- **Encoding:** one byte in `t05`'s `failed.log` was in a legacy code page (the author's shell); it was re-encoded to UTF-8 without reading the file. Readers accept a UTF-8 byte-order mark.
- **Gate allowlist:** Maven Surefire's result summary and setup-java's install line were added to the boilerplate list after two dev cases (`d06`, `d30`) were flagged for sharing them.

## Fixes made by the author after the gates
- `t07` shared distinctive log lines with `d02`; the author rewrote `t07`'s logs, keeping its labels.
- `t15` was missing; the author wrote it.

## Independent validation (before the freeze; the owner's correction 4)
- **Who:** a validator task separate from the author, with no author context. It labelled each item blind (comparability, unverified factors, category, culprit kind and paths) before opening `case.json`, then compared and checked consistency. Same model family as the author: a limitation.
- **What:** every gate- or author-flagged item, plus a seeded random 20% of each split (`random.Random(20261109)`, drawn from the whole split):
  - dev: sample `d02 d05 d06 d10 d16 d20`; validated `d02 d05 d06 d10 d11 d14 d16 d18 d20 d21 d23 d30` (12)
  - test: sample `t01 t04 t06 t12 t14 t15`; validated `t01 t04 t06 t07 t12 t14 t15 t19` (8)
- **Rules, fixed before the verdicts were read:** "agree" keeps the item. Anything else gets one author revision round (reword an unsupported root cause, make a disputed label unambiguous or correct it within the plan row, or fix the data), then one fresh re-validation. Still not "agree": the item moves to `excluded/` and counts in neither split.
- **Results:**
  - test: 8 of 8 agreed in round 1.
  - dev, round 1: 6 agreed (`d05 d06 d10 d16 d20 d30`); 6 did not (`d02 d11 d14 d18 d21 d23`: inconsistent data or narrative, evidence line ranges, one category).
  - dev, round 2: `d02 d14 d18 d23` agreed after revision; **`d11` and `d21` were excluded**. `d11`: the labelled culprit paths left out a third moved file. `d21`: the baseline log states the runner image that `runs.json` and the label call unknown.
  - `d02`: after its round-2 revision (agree), the whole-set anti-template check found its `failed.log` sharing distinctive lines with two test cases. The author rewrote `d02`'s logs (reading the other cases, as during authoring; the engineer did not look at the shared lines), the gates passed, and a fresh validator agreed again (`d02-harbor-settings.r3.json`).
- **Verdicts** are kept in `validation/` (`<id>.json` for round 1, `<id>.r2.json` for round 2).

## Exposure (held-out discipline)
- The authoring driver printed each author task's final message (the case id and any ambiguity it saw) to the engineer's console, for test rows too. Two are known to have been read in full: `t15` (its comparability verdict) and `t07` (its scenario's category). Earlier test-row messages may have been seen in passing; which ones cannot be reconstructed.
- From then on, author and validator tasks on test items answered one word, and only status lines were read.
- No test file was opened. Nothing in the change analysis (baseline choice, factors, ranking weights) changed after M7.3, before any test case existed.

## Final sizes and freeze
- **dev:** 28 cases (30 planned, 2 excluded) · **test:** 30 cases.
- Frozen per split (`MANIFEST.dev.sha256`, `MANIFEST.test.sha256`) and as a whole (`MANIFEST.sha256`), before the protocol (`eval/reports/v11-protocol.md`) and any test run.
