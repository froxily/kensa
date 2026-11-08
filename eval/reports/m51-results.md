# M5.1 results: evaluation set v2, held-out test split

> 2026-10-31. The protocol (`m51-protocol.md`) was committed with the frozen system (`618e4ac`) before the test split was run. This is the first completed run of the v2 test split, and the only one that will be made. Generated tables: `m51-v2-test-comparison.md`, `m51-v2-test.md` (M5.1), `m51-v2-test-m5.md` (M5 baseline). Raw per-case rows are in the matching `.jsonl` files.

## Summary
- **The primary trust goal was not met on held-out cases.**
  - M5.1 gave the strongest status (`corroborated`) to 2–3 wrong answers per configuration. M5 gave its strongest status (`verified`) to 0–1.
  - When M5.1 said `corroborated` it was right 88–90% of the time (100% on dev).
- **For every category except `test_regression`, `corroborated` was right 60 of 60 times.**
- **Every wrong `corroborated` answer was the same kind of claim:** `test_regression`, corroborated by an assertion line together with the *absence* of any cause Kensa recognises. Only three cases were involved:
  - in two (t16, t27) the log does state a database or service cause, in wording Kensa's patterns do not know
  - one (t47) is an insufficient-evidence case
- **Elsewhere M5.1 is clearly better.**
  - **Accuracy:** 41–44/60 against 28–41/60.
  - **Wrong answers:** 3 instead of 9–10 in the two full-text configurations, and 8 instead of 9 in agent + hybrid. Rules only rose from 1 to 3.
  - **Standard and masked cases:** better in seven of the eight comparisons.
  - **Lookalike cases:** not worse.
  - **Citations:** every accepted citation is genuine, and no strongest-status answer carries a rejected citation.
  - **Latency:** no regression.
- **Not tuned.** Nothing has been changed in response to these results. The v2 test split is now spent.

## Protocol adherence
- **Dataset:** `eval/datasets/v2` at digest `b9ed11aff877d65e`, checked by the harness before each run. Both reports state it.
  - The M5 baseline's generated reports (`m51-v2-*-m5.md`) say "eval/datasets/v1" in their header. That is fixed text in M5's report template; their digest lines show the v2 data that was run.
- **Systems:**
  - **M5:** commit `d7c6f56` in a detached worktree, with only the evaluation-harness patch (`m51-baseline-harness.patch`).
  - **M5.1:** commit `618e4ac`. No code, pattern, prompt, threshold or weight changed after the last dev run, and `git diff` showed no code change before the run.
- **Model settings:** the same for both systems (`.env`): `qwen3:4b-instruct-2507-q4_K_M`, temperature 0, seed 42, `num_ctx` 8192, `num_gpu` 99, and `qwen3-embedding:0.6b`. No GitHub access.
- **Coverage:** 4 configurations × 60 cases = 240 investigations per system.
  - An independent read-only check found all 240 in each evaluation database to be v2 test logs (by content hash).
  - All 240 harness rows were paired with their stored diagnoses, with 0 category mismatches.
- **An aborted first attempt (disclosed):**
  - The first attempt began at 11:39 IST. Docker Desktop quit at 12:18 IST while the M5 baseline was at 154 of 240 rows. The M5 run then failed on a database timeout, and the M5.1 run, chained after it, failed at setup.
  - The harness writes its reports only at the end, so the attempt produced no results. Only case ids and configuration names were seen in its log, never an outcome.
  - Both systems were rerun from the start with the identical command at 12:23 IST (recorded in the development notes, 2026-10-31).
- **Post-run review:** the wrong answers were reviewed after the run, for reporting only, as the protocol allows. Nothing was changed as a result.

## Results (v2 test, 60 cases per configuration)

| system | config | correct (95% CI) | incorrect | incorrect, strongest status | incorrect, hedged | incorrect, flagged | abstained correctly / missed | insufficient detected | strongest status correct | citations valid |
|---|---|---|---|---|---|---|---|---|---|---|
| M5 | rules only | 28/60 (0.35–0.59) | 1 | 1 | 0 | 0 | 6 / 31 | 6/6 | 22/23 (96%) | 35/35 |
| M5 | LLM + full text | 38/60 (0.51–0.74) | 10 | 0 | 8 | 2 | 5 / 12 | 5/6 | 13/13 (100%) | 217/240 (90%) |
| M5 | agent + full text | 39/60 (0.52–0.76) | 9 | 0 | 8 | 1 | 5 / 12 | 5/6 | 14/14 (100%) | 190/209 (91%) |
| M5 | agent + hybrid | 41/60 (0.56–0.79) | 9 | 0 | 8 | 1 | 5 / 10 | 5/6 | 13/13 (100%) | 215/227 (95%) |
| **M5.1** | rules only | **41/60** (0.56–0.79) | 3 | **3** | 0 | 0 | 5 / 16 | 5/6 | 23/26 (88%) | 56/56 |
| **M5.1** | LLM + full text | **44/60** (0.61–0.83) | 3 | **2** | 1 | 0 | 5 / 13 | 5/6 | 16/18 (89%) | 195/222 (88%) |
| **M5.1** | agent + full text | **44/60** (0.61–0.83) | 3 | **2** | 1 | 0 | 5 / 13 | 5/6 | 17/19 (89%) | 191/213 (90%) |
| **M5.1** | agent + hybrid (production) | **44/60** (0.61–0.83) | 8 | **2** | 5 | 1 | 5 / 8 | 5/6 | 18/20 (90%) | 204/220 (93%) |

**How to read the columns:**
- **Strongest status:** `verified` (M5) or `corroborated` (M5.1).
- **Hedged:** `supported` or `plausible`.
- **Flagged:** `contradicted` or `conflicting`.
- **Citations valid:** accepted over generated citations in the final answer.

### Accuracy by case kind

| system | config | standard (32) | masked (12) | misleading (6) | lookalike (4) | insufficient (6) |
|---|---|---|---|---|---|---|
| M5 | rules only | 16 | 4 | 2 | 0 | 6 |
| M5 | LLM + full text | 21 | 5 | 4 | 3 | 5 |
| M5 | agent + full text | 21 | 6 | 4 | 3 | 5 |
| M5 | agent + hybrid | 22 | 8 | 4 | 2 | 5 |
| M5.1 | rules only | 22 | 7 | 4 | 3 | 5 |
| M5.1 | LLM + full text | 25 | 7 | 4 | 3 | 5 |
| M5.1 | agent + full text | 25 | 7 | 4 | 3 | 5 |
| M5.1 | agent + hybrid | 24 | 8 | 4 | 3 | 5 |

## The four questions stated in advance

### 1. Do fewer wrong answers carry the strongest status in M5.1 than in M5? **No.**

| config | M5: wrong `verified` | M5.1: wrong `corroborated` |
|---|---|---|
| rules only | 1 (t22) | 3 (t16, t27, t47) |
| LLM + full text | 0 | 2 (t16, t27) |
| agent + full text | 0 | 2 (t16, t27) |
| agent + hybrid | 0 | 2 (t16, t27) |

- **Context, not an excuse:**
  - M5 rarely gave its strongest status on these cases: 13–14 answers in the model configurations, against 18–20 for M5.1.
  - M5 was wrong far more often overall: 28 wrong answers across the three model configurations, against 14 for M5.1. 24 of M5's were `supported`, which its UI showed with a model confidence of 0.7 (supplementary check below).
  - M5.1 also gives more *correct* strongest-status answers: 16–18 against 13–14.
- **But the measure fixed in advance is the wrong strongest-status count, and it rose.**

### 2. When M5.1 says `corroborated`, how often is it right? **88–90%** (23/26, 16/18, 17/19, 18/20)
- **Dev:** 100% in every configuration (28–38 answers). The dev result did not fully transfer.
- **By claimed category:**
  - Every category other than `test_regression`: **60 of 60** `corroborated` answers were right (19/19, 12/12, 14/14, 15/15).
  - `test_regression`: right 3–4 times and wrong 2–3 times per configuration.

| config | `corroborated`, other categories | `corroborated` `test_regression`: right / wrong |
|---|---|---|
| rules only | 19/19 | 4 / 3 |
| LLM + full text | 12/12 | 4 / 2 |
| agent + full text | 14/14 | 3 / 2 |
| agent + hybrid | 15/15 | 3 / 2 |

### 3. Do masked cases improve, without lookalike or standard cases getting worse? **Partly.**
- **Masked:** improved in three configurations (4→7, 5→7, 6→7) and unchanged in agent + hybrid (8→8). This is far below dev's 12/12.
  - The masked cases still missed are t13, t20, t27, t34, t41 and t48, though not every one in every configuration.
  - M5.1 abstained on them, except t27 (wrong, `corroborated`) and t48 in agent + hybrid (wrong, `plausible`).
- **Standard:** up 2 to 6 cases in every configuration.
- **Lookalike:** 3/4 everywhere (M5: 0–3), so there was no over-correction toward environmental causes.
- **Insufficient:** rules only dropped from 6/6 to 5/6. That loss is t47, which rules-only now calls a corroborated test regression.

### 4. Is there a latency regression beyond what GPU state explains? **No.**

| config | M5 wall p50 / p95 s | M5.1 wall p50 / p95 s | M5 model call p50 / p95 s | M5.1 model call p50 / p95 s |
|---|---|---|---|---|
| rules only | 0.3 / 0.5 | 0.2 / 0.3 | — | — |
| LLM + full text | 14.6 / 17.6 | 13.6 / 18.0 | 14.5 / 17.5 | 13.5 / 17.9 |
| agent + full text | 12.4 / 19.9 | 9.7 / 19.0 | 8.1 / 10.3 | 8.2 / 11.0 |
| agent + hybrid | 21.8 / 33.6 | 20.3 / 31.0 | 14.7 / 18.2 | 14.5 / 18.5 |

GPU state was comparable in the two run windows (`nvidia-smi` every 30 s, busy samples only):

| | M5 run (12:23–13:20 IST) | M5.1 run (13:20–14:13 IST) |
|---|---|---|
| busy samples | 74 | 79 |
| median SM clock | 1,335 MHz | 1,335 MHz |
| median power / temperature | 46.4 W / 87 °C (max 96) | 45.8 W / 86 °C (max 94) |
| power limit | 95 W in 74/74 | 95 W in 75/79, 30 W in 4/79 |
| thermal slowdown active | 64/74 | 59/79 |

The total run time was 3,411 s for M5 and 3,195 s for M5.1.

## Why `corroborated` was wrong (post-run review)

| case | label (kind) | what the log states | why Kensa missed it | what was corroborated instead |
|---|---|---|---|---|
| t16 | db_connectivity (misleading) | `curl: (7) Failed to connect to 127.0.0.1 port 48124 … Couldn't connect to server`, the client using the wrong port | no connection-refused pattern knows curl's wording | `FAIL: expected 20 query results, got 0` |
| t27 | db_connectivity (masked) | `Neo.ClientError.Database.DatabaseNotFound … Database does not exist. Database name: herbarium` | the missing-database pattern does not know this wording | `AssertionFailedError: expected: <200> but was: <404>` |
| t47 | unknown (insufficient) | only `assertion failed: healthy`, with the endpoint masked; a failed request or a wrongly rejected response are equally possible | (nothing to find) | `assertion failed: healthy` (rules only; the model configurations said `plausible`) |

**The underlying flaw (D-040, D-041):**
- For a `test_regression` claim, the verifier treats an assertion line as a line that "states a cause". A `test_regression` claim therefore becomes `corroborated` whenever a cited assertion line exists and no environmental cause is recognised.
- An assertion line states a symptom: a test's expectation failed. It does not say why. The "no competing cause" condition only holds as far as the patterns' coverage goes. When a cause is stated in unfamiliar wording, absence of evidence is read as corroboration.
- This is a narrower form of the M5 failure, a surface symptom presented as the cause.
- It never showed on dev, because the dev cases' causes were stated in wording the patterns were developed on. The other 8 wrong M5.1 answers on test were all hedged or flagged.

## The deterministic fallback (D-044) on held-out cases
The fallback replaced the model's final answer 13 times: 5 in LLM + full text and 4 in each agent configuration. The counts come from the stored verification notes; the harness does not record them.

| case | model's final answer (set aside) | reported instead | correct? |
|---|---|---|---|
| t12, t36, t43 (each in all three model configurations) | `unknown` (`not_established`) | `dependency_build` (`corroborated`) | yes, 9 times |
| t58 (LLM + full text) | `docker` (`conflicting`) | `test_regression` (`corroborated`) | yes |
| t27 (all three model configurations) | `unknown` (`not_established`), once after naming `db_connectivity` with citations that failed the checks | `test_regression` (`corroborated`) | **no, 3 times** |

- **Net effect:** 10 abstentions or flagged answers became correct, and 3 abstentions became wrong `corroborated` answers.
- **The risk D-044 named in advance happened, once per configuration.** If the rules corroborate a wrong cause, the fallback turns an abstention into a confident wrong answer.
- **Derived from the stored notes, not a separate run:** without the fallback, the model configurations would have scored:
  - 40/60, 41/60 and 41/60 correct
  - 1 wrong `corroborated` answer each (t16), and 4 more missed abstentions each

## Other wrong answers (hedged or flagged; shown with their status)
- **Agent + hybrid has five hedged wrong answers** where the full-text configurations abstained or were right:
  - t05: lookalike, said `missing_env_var`
  - t25: said `missing_env_var` instead of `db_connectivity`
  - t30: misleading, said `missing_env_var` instead of `workflow_path`
  - t47: insufficient, said `test_regression`
  - t48: masked, said `test_regression` instead of `workflow_path`
- **It also has one flagged answer:** t60, `dependency_build` (`conflicting`) instead of `docker`.
- **In the full-text configurations** the only hedged wrong answer is t47 (`plausible`).

## Abstentions
- **Correct abstentions:** M5.1 abstained correctly on 5 of the 6 insufficient cases in every configuration. On t47 the model configurations said `plausible` and rules-only said `corroborated`.
- **Missed causes (abstained on a case with a known cause):**
  - M5.1: 8–16 per configuration, on 20 distinct cases. M5: 10–31, on 33 cases.
  - Missing a cause is the safe failure: the UI shows no cause, only the evidence and the rule hint.
  - The commonest misses are causes the patterns do not recognise. In t13 and t34 (masked), M5 hedged a wrong `test_regression` while M5.1 abstained.

## Citation validity (independent re-check)
- **Method:** a read-only script, separate from the verifier, compared every accepted citation's quote with its cited line in the stored evidence.
- **M5.1:** all **646** accepted citations matched; 65 were rejected and never shown.
- **M5:** all 657 matched; 54 were rejected.
- **Strongest status:** no `corroborated` or `verified` diagnosis carried a rejected citation.
- **Model configurations:** the share of generated citations that were valid was 88–93% for M5.1, against 90–95% for M5.

## Dev and held-out
| config | M5 dev | M5 test | M5.1 dev | M5.1 test |
|---|---|---|---|---|
| rules only | 34 | 28 | 55 | 41 |
| LLM + full text | 40 | 38 | 54 | 44 |
| agent + full text | 41 | 39 | 54 | 44 |
| agent + hybrid | 43 | 41 | 53 | 44 |

- **The gap:** the cause patterns were developed on the dev split, and their gain on test is about half of the dev gain.
- **Masked cases:** 12/12 on dev, but 7–8/12 on test.
- **Strongest-status precision:** 100% on dev, but 88–90% on test.
- **What carried over:** the ordering (M5.1 better than M5 in every configuration).
- **The intervals:** with 60 cases they are about ±0.11. Only two differences are clearly outside noise: the rules-only gain (+13) and the drop in wrong hedged answers in the full-text configurations (8 → 1). The model configurations' accuracy gains (+3 to +6) are not.

## Supplementary (not a protocol metric): what M5 displayed
- **What M5's UI showed:** the model confidence, capped by status.
- **What it showed for wrong answers on this split:** 0.7 on 8 of the 9–10 per model configuration (`supported`), 0.4 on the `contradicted` ones, and 0.9 on rules-only's one wrong `verified` answer.
- **M5.1:** shows no confidence, only the status and its explanation. Its explanation for `corroborated` already says "strong evidence, not proof".

## Limitations
- **Data:** 60 synthetic cases per split from one separate LLM author. Differences of 3–4 cases are within noise.
- **Scoring:** the category is the proxy for the root cause. Root-cause wording was reviewed only for the wrong answers.
- **The dev and test splits share an author and a style.** Real CI logs will contain more unfamiliar wordings, so the pattern-coverage problem above should be expected to be larger in practice, not smaller.
- **Remediation:** no proposal or diff is claimed to be semantically correct or safe.

## What follows (no change made)
- **No fix is evaluated in this report.** The v2 test split is spent. The protocol says any later change is evaluated on a new set.
- **A change suggested by the review, as a principle rather than a pattern:**
  - An assertion line should never by itself corroborate a cause. It is a symptom.
  - With that rule, `test_regression` would be at most `plausible` unless something positively points at the code under test. Examples would be a change to the asserted code or a stack trace inside it, with no unexplained environment errors.
  - On this split it would have moved the 3–4 correct and 2–3 wrong `corroborated` test regressions per configuration to `plausible` (the table under question 2). Their category would be unchanged unless the fallback had produced them.
  - The deterministic fallback would then no longer report a test regression.
  - Adding curl's or Neo4j's wording to the patterns would fix t16 and t27, but that would be tuning on the test answers.
- **Its effect is unmeasured.** A dev-split check would only show regressions. A new, independent set (v3) is needed to measure it.
