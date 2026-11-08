# Evaluation dataset v2: authoring record

## Authorship and independence
- **Author:** every case and label was written by **Codex** (OpenAI, via the owner's ChatGPT login) acting as an independent author.
  - Claude, which builds Kensa, wrote the specification (`AUTHORING_SPEC.md`), the per-case plan (`plan.csv`: split, category, kind and a note per id) and the quality gates.
  - Claude wrote **no case content and assigned no labels** beyond the plan's category and kind.
- **Isolation:** Codex was told to read nothing outside `eval/datasets/v2/`: not `backend/`, `frontend/`, `scripts/`, `knowledge/`, `eval/datasets/v1/`, `eval/reports/`, `.github/` or any root document. It ran no project code and used no network.
- **Held-out split:** the test split (`t01`–`t60`) is never opened by Claude. The gates report case ids and problem types only.
- **Knowledge base:** unchanged since M2 (`knowledge/`, last changed before v1 was read).

## Why v2 exists
v1's held-out split was used once in M5 and is spent (D-039). M5's review found that most wrong answers named a surface symptom (a failing test, a Docker build error) instead of the underlying cause. v2 measures exactly that, with three times more cases per split.

## Distribution (per split; `plan.csv`)
| kind | cases | what it tests |
|---|---|---|
| standard | 32 (4 per category) | the cause is shown in its own category's terms |
| masked | 12 | the job's final failure is reported by another tool (test runner, Docker build or push, script), while the log still shows the underlying cause |
| misleading | 6 | a prominent error points at the wrong category |
| lookalike | 4 | the cause really is the labelled category, but the output uses wording typical of another; guards against over-correcting toward "environmental" causes |
| insufficient | 6 (`unknown`) | 2 generic exits, 2 truncated logs, 2 with two equally plausible causes |

Ground-truth rule: the category is what must change to fix the failure (tie-breakers in `AUTHORING_SPEC.md`).

## Quality gates (`scripts/freeze_dataset.py --dataset v2`)
- **Loading and shape:**
  - every case loads, with exact evidence ranges inside the cited file
  - logs have 50–140 lines
  - 3–6 repository files per case, including the workflow
- **Plan conformity:** id prefix, split, category and kind equal the plan row.
- **No leaks:**
  - no credential-like strings
  - no log line names the root cause or addresses a model
- **Anti-template check:** no two v2 logs, and no v2 log and v1 log, share more than 25% of their non-trivial lines.
  - Standard runner, checkout, BuildKit and setup-action lines are excluded by an **explicit allowlist**, never by corpus frequency.
  - The allowlist entries added for v2 apply to v2 only; v1's gates stay as they were when it was frozen. They cover:
    - the hosted-runner banner
    - actions/checkout's post-job clean-up
    - BuildKit's header
    - the setup-go/java/node/ruby/php/beam actions' fixed lines
    - Gradle's and `dotnet test`'s fixed banner, task and summary lines
    - Maven's banner and failure footer
    - pytest's section banners and header
    - pip's install lines
  - **Flagged test-split pairs:** Claude does not inspect them, because that would expose test content. Codex, as the author, reviews them and revises the cases if needed.
    - action inputs echoed under `with:`
    - masked `***` values
  - For v2 a pair counts as templated only when it shares at least 3 such lines. Two short logs of the same category can legitimately share one genuine error message, such as GitHub CLI's 403 line.
  - All allowlist entries were added after inspecting the shared lines of flagged **dev** pairs. They are standard tool output, not case content.
- **Commentary check:** upper-case `NOTE:` only. Tools print lower-case notes, such as rustc's `note: run with RUST_BACKTRACE=1`.

## History
1. **Authoring runs:** Codex wrote the cases in short resumed runs of about five cases each. Runs that ended early did so without error or limit; the next run continued from the first missing id.
2. **d01:** Claude wrongly reported d01's workflow missing; `ls -R` had skipped the hidden `.github` folder. Codex found the workflow present and corrected only d01's log evidence range.
3. **d08:** Codex corrected one evidence range during its own line check.
4. **Brief changes:** from d21 the brief asked for more substantial failing-step output, because several early logs had fewer than ten non-boilerplate lines.
5. **Fixes after the gates flagged them:**
   - **d38:** written as `misleading` against its plan row `standard`. Codex rewrote it as a standard case; the plan's label stands.
   - **d32:** too close to d20 (both Kotlin/Gradle jobs with an unreachable MySQL service). Codex rewrote it with a different service and tooling.
6. **Toolchain variety:** from d51 the brief asks Codex to vary toolchain versions and project layout when an ecosystem repeats.
7. **Dev freeze:** after d60, the dev split was frozen on its own (`MANIFEST.dev.sha256`, 2026-10-31) and used for development while the test split was being written. The final freeze checks that no dev file changed since then.
8. **Test split (t01–t60):** written in the same way. The test brief also required distinctness from every dev case. Recorded by id only, because Claude does not read test cases:
   - **t35:** flagged against t12 by the similarity gate; Codex rewrote it.
   - **t40:** flagged against the dev case d33; Codex rewrote it from scratch, and d33 was not touched. A test case must not resemble a dev case.
   - **t46–t50:** a Codex run stopped at a usage limit after writing t46–t49. Authoring paused until the owner approved resuming after the reset. Codex then re-checked t46–t49, found them complete, and wrote t50.
   - **Final review:** Codex reviewed all 60 test cases against the specification and changed six, with no label changed:
     - t03, t27 and t51: overlapping build-tool output replaced
     - t12: replaced a failure close to another case
     - t26: replaced a repeated scenario
     - t11: corrected an evidence range
