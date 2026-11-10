# Evaluation dataset v4-history: authoring record

A fresh set for fingerprint version 3 (D-057), written after version 2 missed its held-out thresholds on v3-history. Same procedure as v3-history, with a wider range of tools and ecosystems.

## Authorship and independence
- **Author:** a separate LLM author wrote every sequence and every label: the four logs and `sequence.json` (cluster, relation, category, title, root cause). Each sequence was written by a fresh, isolated task.
- **The engineer who builds Kensa** wrote the specification (`AUTHORING_SPEC.md`), the per-sequence plan (`plan.csv`: split, cluster pattern, focus, suggested ecosystem; committed in `1f944a6` before any sequence was written) and the quality gates (`scripts/freeze_v3.py`). They wrote no log content and assigned no labels beyond the plan's pattern.
- **Isolation:** each author task read only `AUTHORING_SPEC.md`, `plan.csv` and the existing v4 sequences (to avoid reusing names and lines). It ran no project code and used no network. It never saw Kensa's code, its fingerprint rules or the earlier datasets.
- **Held-out split:** the test sequences (`ht31`–`ht60`) were never opened by the engineer. See "Exposure".

## Design
- **30 sequences per split, 4 entries each (120 entries per split before exclusions).**
- **Patterns** (`plan.csv`, the same multiset in both splits), for example `a b~a a c` (a recurrence after a look-alike), `a a b~a a`, `a b a b`, `a b~a c d~c`. `b~a` is a new cluster written as a look-alike of `a`.
- **Breadth:** each row names a focus (for example a missing variable, a module, a dependency resolution, a test assertion, a port, an image, a permission, memory or time) and one of 30 suggested ecosystems, each used once per split: Python (pytest; mypy and ruff; poetry and uv), Node (jest; pnpm; yarn and vitest; Playwright), Deno or Bun, Go, Rust, C++, Java (Maven; Gradle), Kotlin and Android, Scala or Clojure, .NET, Ruby, PHP, Elixir, Swift, Dart or Flutter, Bazel, Docker, Kubernetes, Terraform, Ansible or Packer, database service containers, GitHub Actions cache and artifacts, release tooling, and shell and make.

## Quality gates (`scripts/freeze_v3.py --dataset v4-history`)
The same gates as v3-history: loading and shape (4 entries, 40–130 lines, the plan row's pattern), UTF-8, no near-copy recurrences, no credential-like strings, no giveaway commentary, and an anti-template check across sequences (standard runner lines excluded by an explicit list).

## Fixes made by the author after the gates
Each fix was a fresh author task given the gate message and told to keep every label unchanged.
- **dev:** `hd35` (giveaway commentary in three logs), `hd48` and `hd50` (near-copy recurrences). `hd52` still had near-copy recurrences after two fixes and was **excluded**.
- **test:** `ht41` (giveaway commentary), `ht46`, `ht50` and `ht56` (near-copy recurrences), and `ht43`, `ht48`, `ht51`, `ht57` (logs sharing distinctive lines with another sequence). `ht50` needed a second round (still a near copy, and one log then shared lines with `hd50`).
- No fix was made by the engineer.

## Independent validation (before the freeze)
- **Who:** a validator task separate from the author, with no author context. It read the four logs in order and labelled each entry blind (cluster, relation, category) before opening `sequence.json`, then compared (clusters up to renaming) and checked consistency. Same model family as the author: a limitation.
- **What:** every sequence changed after a gate finding, plus a seeded random 20% of each split (`random.Random(20261110)`, drawn from the whole split):
  - dev: sample `hd36 hd40 hd49 hd51 hd53 hd54`; validated `hd35 hd36 hd40 hd48 hd49 hd50 hd51 hd53 hd54` (9)
  - test: sample `ht36 ht41 ht42 ht46 ht52 ht54`; validated `ht36 ht41 ht42 ht43 ht46 ht48 ht50 ht51 ht52 ht54 ht56 ht57` (12)
- **Rules, fixed before the verdicts were read:** "agree" keeps the sequence. Anything else gets one author revision round, then one fresh re-validation. Still not "agree": the sequence moves to `excluded/` and counts in neither split.
- **Results:**
  - dev, round 1: 4 agreed (`hd35 hd49 hd50 hd51`); 5 did not.
  - dev, round 2: `hd36 hd40 hd48 hd54` agreed after revision; **`hd53` was excluded** (disputed categories and a relation: whether a deadlock that shows up as a timeout is a test regression or a timeout).
  - test, round 1: 7 agreed (`ht36 ht41 ht43 ht50 ht52 ht54 ht57`); 5 did not.
  - test, round 2: `ht42 ht46 ht48` agreed after revision; **`ht51` (ambiguous categories) and `ht56` (a disputed relation) were excluded**.
- After the revisions, the gates were run again on both splits and passed.
- **Verdicts** are kept in `validation/` (`<id>.json` for round 1, `<id>.r2.json` for round 2).

## Exposure (held-out discipline)
- Author, gate-fix, revision and validator tasks on test items answered one word, and their drivers printed only status lines. The engineer saw test ids, gate messages (kind of problem and a share of lines), verdict words, disputed field names and reason codes; no test log or label.
- Authoring stopped once at a usage limit (48 of 60 sequences) and resumed after the reset with the same prompts.
- Fingerprint version 3 was designed on v3-history dev and v4-history dev only, and frozen (committed) before the test split ran.

## Final sizes and freeze
- **dev:** 28 sequences, 112 entries (30 planned, 2 excluded) · **test:** 28 sequences, 112 entries (30 planned, 2 excluded).
- Frozen per split (`MANIFEST.dev.sha256`, `MANIFEST.test.sha256`) and as a whole (`MANIFEST.sha256`), before the protocol (`eval/reports/v110-protocol.md`) was committed and before any test run.
