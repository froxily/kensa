# Evaluation dataset v3-history: authoring record

## Authorship and independence
- **Author:** a separate LLM author wrote every sequence and every label: the four logs and `sequence.json` (cluster, relation, category, title, root cause). Each sequence was written by a fresh, isolated task.
- **The engineer who builds Kensa** wrote the specification (`AUTHORING_SPEC.md`), the per-sequence plan (`plan.csv`: split, cluster pattern, focus, suggested ecosystem) and the quality gates (`scripts/freeze_v3.py`). They wrote no log content and assigned no labels beyond the plan's pattern.
- **Isolation:** each author task was told to read only `AUTHORING_SPEC.md`, `plan.csv` and the existing sequences (to avoid reusing names, and for test rows to stay clearly different from dev sequences). It ran no project code and used no network.
- **Held-out split:** the test sequences (`ht01`–`ht20`) were never opened by the engineer. Gate messages, verdict words and disputed field names were seen; see "Exposure" for the rest.

## Design
- **20 sequences per split, 4 entries each (80 entries per split).** The plan's earlier "40 + 40 cases" became sequences, because pairs of entries, not cases, are the unit of the metrics.
- **Patterns** (`plan.csv`, the same multiset in both splits): for example `a b~a a c` (a recurrence after a look-alike), `a a b~a a`, `a b a b`, `a b~a c d~c`, `a a a b`. `b~a` is a new cluster written as a look-alike of `a`.

## Quality gates (`scripts/freeze_v3.py --dataset v3-history`)
- **Loading and shape:** every sequence loads; 4 entries; logs 40–130 lines; the entries follow the plan row's pattern (clusters and relations).
- **Encoding:** every file is UTF-8.
- **No copies:** a recurrence is not a near copy of an earlier entry (at most a set share of identical lines).
- **No leaks:** no credential-like strings; no giveaway commentary.
- **Anti-template check across sequences:** no two logs of different sequences share 3 or more distinctive lines above a set share; standard runner and setup lines are excluded by an **explicit list**.

## Fixes made by the engineer (mechanical, no content judgement)
- **Encoding:** one byte in `hd08`'s `e3.log` was in a legacy code page (the author's shell); it was re-encoded to UTF-8. Readers accept a UTF-8 byte-order mark.

## Fixes made by the author after the gates
- `ht05`: entry `e4` did not follow its plan row's pattern; the author corrected its relation.
- `ht15`–`ht20`: missing or incomplete; the author wrote them.
- `ht16`: `e4` was a near copy of `e1`; the author rewrote it with realistic differences.
- `ht17`: two logs shared distinctive lines with `ht07`; the author rewrote them.

## Independent validation (before the freeze; the owner's correction 4)
- **Who:** a validator task separate from the author, with no author context. It read the four logs in order and labelled each entry blind (cluster, relation, category) before opening `sequence.json`, then compared (clusters up to renaming) and checked consistency. Same model family as the author: a limitation.
- **What:** every gate- or author-flagged sequence, plus a seeded random 20% of each split (`random.Random(20261109)`, drawn from the whole split):
  - dev: sample `hd07 hd12 hd16 hd20`; validated `hd02 hd04 hd05 hd06 hd07 hd09 hd12 hd16 hd18 hd19 hd20` (11)
  - test: sample `ht06 ht10 ht11 ht20`; validated `ht02`–`ht15`, `ht17`, `ht20` (16)
- **Rules, fixed before the verdicts were read:** "agree" keeps the sequence. Anything else gets one author revision round, then one fresh re-validation. Still not "agree": the sequence moves to `excluded/` and counts in neither split.
- **Most disputes were about the `root_cause` text** (not scored): the validator often found that a log shows the failure but not the stated mechanism. Revisions reworded those texts or added realistic log evidence.
- **Results:**
  - test, round 1: 7 agreed (`ht02 ht03 ht08 ht09 ht13 ht14 ht20`); 9 did not.
  - test, round 2: `ht04 ht07 ht10 ht11 ht12 ht15 ht17` agreed after revision; **`ht05` and `ht06` were excluded** (a disputed relation: whether a new cluster is a look-alike of an earlier one).
  - dev, round 1: 2 agreed (`hd07 hd09`); 9 did not.
  - dev, round 2: `hd02 hd04 hd05 hd12 hd16 hd18 hd19 hd20` agreed after revision; **`hd06` was excluded** (the same relation dispute).
  - `ht15`: after its round-2 revision (agree), the near-copy gate found `e2` 85% identical to `e1`. The author rewrote `e2` with realistic differences, the gates passed, and a fresh validator agreed again (`ht15-thimble-dredge.r3.json`).
  - `hd05`: its first revision was validated "agree", but the driver stopped before recording it and its restart revised `hd05` a second time. The final content was validated again by a fresh validator (agree). Both verdicts are kept.
- **Verdicts** are kept in `validation/` (`<id>.json` for round 1, `<id>.r2.json` for round 2).

## Exposure (held-out discipline)
- The authoring driver printed each author task's final message to the engineer's console, for test rows too. One is known to have been read in full: `ht05` (its scenario, during the plan-conformity fix). Earlier test-row messages may have been seen in passing; which ones cannot be reconstructed.
- From then on, author and validator tasks on test items answered one word, and only status lines were read.
- No test file was opened. Fingerprint version 2 was developed on the dev split and finished before that message; nothing in Kensa changed after it.

## Final sizes and freeze
- **dev:** 19 sequences, 76 entries (20 planned, 1 excluded) · **test:** 18 sequences, 72 entries (20 planned, 2 excluded).
- Frozen per split (`MANIFEST.dev.sha256`, `MANIFEST.test.sha256`) and as a whole (`MANIFEST.sha256`), before the protocol (`eval/reports/v11-protocol.md`) and any test run.
