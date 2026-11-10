# Changelog

All notable changes to Kensa. Versions follow [Semantic Versioning](https://semver.org/). Measured results are in [`docs/evaluation.md`](docs/evaluation.md) and [`eval/reports/`](eval/reports).

## [1.1.0] - 2026-11-10

Failure intelligence: Kensa now looks beyond the single failed run. Change-aware investigation and CI failure analytics are available; historical recurrence matching is experimental and off by default. No improvement in the final AI diagnosis accuracy has been shown.

### Added
- **Change-aware root-cause investigation.** For an imported GitHub run, Kensa finds the last comparable successful run of the same workflow and ranks the changes in between (D-054).
  - Comparability is checked factor by factor (workflow file, event, branch, job and matrix, runner labels, runner image); anything it cannot verify is named, never treated as equal.
  - Suspected changes are correlations, never causes, and diff hunks can support a claim but never corroborate it.
  - Held-out evaluation (30 unseen cases): the breaking change ranked first in 81% of culprit cases (largest diff: 48%, most recent: 24%); comparability verdict right in 30 of 30.
  - Change evidence added no wrong `corroborated` answer, but no accuracy gain either: the same 26 of 30 diagnoses were right with and without it.
- **Historical failure intelligence (experimental, off by default).** Every investigation records versioned failure fingerprints (D-053, D-057).
  - Only an *exact* fingerprint, built from something the log names (a variable, module, test and assertion, image, file, port or database), can claim a recurrence; approximate ones only suggest similar failures, listed apart and never called the same failure.
  - History is never evidence and never changes a diagnosis; an operator can record a confirmed resolution.
  - Held-out evaluation on a fresh set (28 sequences, run once): precision 1.000 and no look-alike merged, but recall 0.349 (target 0.60) and similar-failure Recall@5 0.892 (target 0.90). Matching is therefore off by default (`KENSA_HISTORY_MATCHING=true` turns it on, labelled experimental).
- **CI failure analytics with incremental ETL.** Track public repositories (read-only, budgeted, resumable syncs) and see failure trends, categories, workflows, data freshness and data quality, with every chart also given as a table (D-052, D-055). Recurring failures appear only when history matching is turned on.
  - Load benchmark on synthetic rows (50,000 runs, 250,000 jobs, 5,000 investigations): dashboard p95 80 ms with matching off and 120 ms with it on (target below 300 ms); a second full refresh gives identical rows.
- **Forget repository and retention** delete everything derived from a repository or an old investigation, down to checkpoints, fingerprints and analytics rows.
- **The replay demo** is re-recorded for v1.1.0 (seven real runs with the local model) and shows the change panel, the History panel in its default state and the dashboard, labelled as prerecorded and synthetic where they are. It works offline.

### Changed
- Model conclusions are no longer indexed as evidence for later investigations (`index_incidents` off by default, D-051).
- An imported job that was already investigated opens the existing investigation instead of a duplicate.

### Fixed (found while hardening v1.1)
- A history sync no longer stops on a malformed GitHub record, no longer marks a window over GitHub's 1,000-result listing limit as complete, re-reads interrupted earlier attempts, and rotates its pending queue.
- Analytics count a run once it has an outcome, and refreshes of one workspace no longer collide.
- An investigation's log is always listed first: a GitHub import with diff documents could show a diff in place of the log.

### Migrations
`0008_history` to `0012_fingerprint_kind`: additive, each with a downgrade. A v1.0 database upgrades with every existing row unchanged (tested).

## [1.0.0] - 2026-11-08

First public release: local-first investigation of failed GitHub Actions runs with cited, verified root-cause diagnoses, human-approved remediation proposals, an English and Japanese UI, and a static replay demo.
