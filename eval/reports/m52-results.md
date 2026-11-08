# M5.2 results: a test regression is never corroborated (D-046)

> 2026-11-02. M5.2 changes one rule, chosen by the owner after reviewing M5.1's held-out result (`m51-results.md`, D-045). It is committed as `5f001dc`. This report has two parts: a regression check on the v2 **dev** split, and a derivation on the v2 **test** split. **The test split was spent by M5.1, so nothing here is a held-out result**, and nothing was tuned on its answers. Generated tables: `m52-v2-dev.md`, `m52-v2-dev-comparison.md`, `m52-v2-test-derived-comparison.md`; raw rows in the matching `.jsonl` files.

## Summary
- **What M5.2 guarantees:** a test regression is never `corroborated`, so the deterministic fallback can no longer report one. On M5.1's held-out run, every wrong `corroborated` answer was a test regression.
- **v2 dev regression check, run once on the four configurations:**
  - No wrong answer is `corroborated`, and `corroborated` is right every time it is given (33/33, 27/27, 28/28, 24/24).
  - **Correct:** 55, 52, 53 and 53 of 60 (M5.1's last dev run: 55, 54, 54, 53).
  - **Lost to D-046:** one lookalike case, d58, in LLM + full text. The fallback no longer replaces the model's flagged `missing_env_var` with the correct test regression.
  - **Lost to model variation, not D-046:** d51 in LLM + full text, and d58 in agent + full text, where the model's second attempt abstained this time.
  - Everything else that changed is a correct test regression now shown as `plausible`, plus one status change from variation.
- **The spent v2 test split, derived exactly from M5.1's stored run (not a held-out result):**
  - Wrong `corroborated` answers fall from 2–3 to 0 per configuration, by construction.
  - Correct answers go from 41/44/44/44 to 41/43/44/44. The fallback no longer reports t27 wrong, and no longer rescues t58.
- **Cost:** correct test regressions are shown as hypotheses, and the fallback rescues fewer cases. Measured so far: 1 of 240 answers on dev and 1 of 240 on the spent test split, both lookalike cases in LLM + full text.
- **Not measured:** whether this holds on new failures. Both v2 splits shaped this rule, so measuring it needs a new independent set (v3).

## The change
- **The rule (D-046):** the verifier never gives `corroborated` to a `test_regression` claim. It stays at most `plausible`, with the note "a failing assertion shows that a test failed, not why: the log cannot show that the code under test changed, and a cause stated in unfamiliar wording would not be recognised".
- **Why:** on M5.1's held-out run, every wrong `corroborated` answer (9 across the four configurations) was a test regression, corroborated by an assertion line plus the *absence* of a recognised cause. For every other category `corroborated` was right 60 of 60 times. The mechanism is general: an assertion states a symptom, and "no competing cause" only means none was recognised.
- **What follows from it:**
  - The deterministic fallback (D-044) only reports `corroborated` diagnoses, so it can no longer report a test regression.
  - Test regressions are no longer indexed as past incidents, and their stored confidence is capped at 0.6, like every `plausible` answer.
- **Unchanged:** every other category and check, the classifier, the cause patterns, the prompt, the model, and the model calls. Retries depend on the verifier's `retryable` flag, which neither `corroborated` nor `plausible` sets, so the model is asked exactly the same questions as before.
- **Not added:** a pattern for curl's or Neo4j's wording (the two causes M5.1 missed on test). That would have been tuning on the test answers.
- **Tests:** two new tests fail on the M5.1 verifier and pass on M5.2: an assertion alone never corroborates a test regression, and the fallback never reports one (while still replacing an abstention with a stated missing variable).

## v2 dev regression check (`m52-v2-dev-comparison.md`)
**Run:** 2026-11-01 23:40 to 2026-11-02 00:49 IST, commit `5f001dc`.
- **Setup:** the four M5.1 configurations on the 60 dev cases, in a separate evaluation database (`kensa_eval_m52dev`), so M5.1's held-out data stays intact. Same model settings as M5.1: `qwen3:4b-instruct-2507-q4_K_M`, temperature 0, seed 42, `num_ctx` 8192, `num_gpu` 99, `qwen3-embedding:0.6b`.
- **Completeness:** exit 0, no errors, 240 rows. The dev split is unchanged since M5.1 (its own digest, `56d310bdc26987fe`, still matches).
- **Compared with:** M5.1's last dev run (`m51-dev-iter2`). That run was made on the M5.1 code before it was committed as `618e4ac`, so its report header shows the HEAD at the time, `d7c6f56`. M5.1's records state that nothing affecting diagnosis changed between that run and the commit. Since then, the only code change is the verifier (`git diff 618e4ac 5f001dc -- backend/src`).

| config | correct, M5.1 → M5.2 | wrong with the strongest status | wrong, all | `corroborated` right | model calls | model call p50 / p95 s |
|---|---|---|---|---|---|---|
| rules only | 55 → 55 | 0 → 0 | 0 → 0 | 38/38 → 33/33 | — | — |
| LLM + full text | 54 → **52** | 0 → 0 | 3 → 5 | 31/31 → 27/27 | 60 → 60 | 15.3 / 18.1 → 17.2 / 22.2 |
| agent + full text | 54 → **53** | 0 → 0 | 3 → 4 | 31/31 → 28/28 | 87 → 90 | 9.2 / 12.0 → 8.8 / 10.7 |
| agent + hybrid | 53 → 53 | 0 → 0 | 3 → 3 | 28/28 → 24/24 | 91 → 91 | 16.2 / 19.0 → 17.8 / 23.5 |

**Every change, case by case** (from the raw rows, and the stored diagnoses and events in `kensa_eval_m52dev`):

| change | rules | LLM + FT | agent + FT | agent + hybrid | cause |
|---|---|---|---|---|---|
| correct test regression, `corroborated` → `plausible`, same category | 5 | 2 | 2 | 4 | D-046 (the intended relabel) |
| d58 (lookalike): correct `test_regression` (`corroborated`) → `missing_env_var` (`conflicting`), **wrong** | — | 1 | — | — | D-046, through the fallback |
| d58 (lookalike): the same change | — | — | 1 | — | model run-to-run variation (the second attempt abstained) |
| d51 (lookalike): correct `test_regression` (`plausible`) → `db_connectivity` (`conflicting`), **wrong** | — | 1 | — | — | model run-to-run variation |
| d50: `dependency_build`, `corroborated` → `plausible` (a citation rejected), still correct | — | 1 | — | — | model run-to-run variation |

- **d58** looks like a missing variable but is a test regression. In both full-text model configurations, M5.2's model first named `missing_env_var`, and the verifier flagged it as conflicting with the signature rules.
  - **LLM + full text (D-046):**
    - M5.1's stored answer matches the rules' own diagnosis exactly (3/3 citations, the same fix-keyword result as rules only), while the model's answer cites 4 lines. The model's prompt was the same size in both runs.
    - So M5.1's fallback had replaced the flagged answer with the rules' `corroborated` test regression, which was right.
    - Under D-046 the rules' diagnosis is `plausible`, so the fallback does not fire and the flagged answer stands. This is the dev counterpart of t58 on the test split.
  - **Agent + full text (variation):**
    - M5.1's stored answer does not match the rules' diagnosis (4/4 citations, fix keyword found), so it was the model's own second attempt.
    - This time that second attempt answered `unknown` (stored events), so the flagged first answer was kept.
    - Had it named `test_regression` again, M5.2 would have kept that as `plausible`, which ranks above `conflicting`.
  - **Agent + hybrid:** the model said `test_regression` itself, which is unaffected.
- **d51 and d50 are not D-046:**
  - In LLM + full text the only model call happens before the verifier runs, and the harness does not index incidents. So the change cannot reach that call, and neither answer is a test regression that D-046 relabelled.
  - The recorded prompt sizes differ slightly between the two runs on d51 and on two unchanged cases (31–303 tokens). The harness records Ollama's `prompt_eval_count`, which may leave out tokens reused from Ollama's cache, so this does not show that the inputs differed.
  - Exactly why the model answered differently was not traced.
- **The other kinds hold:** standard 28–29/32, masked 12/12, misleading 5/6 and insufficient 4–6/6 are unchanged in every configuration. Lookalike cases fell in the two full-text configurations (4/4 → 2/4 and 3/4) because of d58 and d51.
- **Model calls are unchanged where the model answered the same,** as expected: retries do not depend on the relabel. Agent + full text made 3 more calls: d50, d51 and d53 each needed a second attempt this time, and ended with the same answer as before. A retry follows only a `conflicting` or `not_established` first attempt, which D-046 cannot produce, so these first attempts varied from run to run.
- **Latency:** no change can be attributed to D-046, which adds one comparison in the verifier and no model call.
  - **Model call times:** paired by case, the median model call took 1.11×, 0.94× and 1.03× as long as in M5.1, in LLM + full text, agent + full text and agent + hybrid.
  - **GPU state** does not explain the slower configurations: it was faster this time (median busy clock 1,237 MHz at a 95 W limit, against 1,076 MHz at 75 W in M5.1's dev run). It was thermally throttled in 71 of 97 busy samples (M5.1: 79 of 84).
  - **Rules only**, which calls no model, also took longer (wall p50 0.3 → 0.5 s), so the machine was probably busier in general. CPU and memory load were not measured.
  - Agent + hybrid's wall time rose more (p50 26.1 → 30.9 s) than its model calls (16.2 → 17.8 s), which fits the same explanation.

## The spent v2 test split, derived (not a held-out result)
**Method.** Because D-046 changes only the verifier's final label, M5.2's answers on the test split follow exactly from M5.1's stored run (`kensa_eval`, `618e4ac`) without running the model again (`m52-v2-test-derived.jsonl`):
- a corroborated `test_regression` becomes `plausible`, with its category unchanged
- where the fallback had reported a test regression, the model's set-aside answer, as recorded in the fallback's note, is reported instead (an abstention if its status was `not_established`)
- every other answer is unchanged

**Why this is exact, not an estimate** (checked in the code at `5f001dc`):
- The model is asked the same questions. Only `conflicting` and some `not_established` results are retryable, so a test regression's attempt, `corroborated` before or `plausible` now, is always the last one.
- The agent keeps the same attempt. It picks the latest attempt whose status ranks at least as high as the best so far, and every earlier attempt was `conflicting` or `not_established`, both ranked below `plausible`.
- The fallback cannot newly fire. A test regression was `corroborated` only when no other cause was stated in the log, so the rules could not have corroborated a different cause for the same case.
- No case affects another: the harness turns off incident indexing.

Citation counts and latency are carried over from M5.1 and were not re-derived: the set-aside answers' citations are not stored.

| config | M5.1 correct → M5.2 | wrong with the strongest status | wrong, all | missed abstentions | `corroborated` right |
|---|---|---|---|---|---|
| rules only | 41 → 41 | 3 → **0** | 3 → 3 | 16 → 16 | 23/26 → 19/19 |
| LLM + full text | 44 → **43** | 2 → **0** | 3 → 3 | 13 → 14 | 16/18 → 12/12 |
| agent + full text | 44 → 44 | 2 → **0** | 3 → 2 | 13 → 14 | 17/19 → 14/14 |
| agent + hybrid | 44 → 44 | 2 → **0** | 8 → 7 | 8 → 9 | 18/20 → 15/15 |

- **By construction, no wrong answer carries the strongest status,** and `corroborated` is right every time it is given. This is the property D-046 guarantees, not evidence that it generalises: the rule was chosen after seeing these cases.
- **What changed, case by case:**
  - **7 rules-only and 4 per model configuration:** corroborated test regressions (right and wrong) now `plausible`, with the same category.
  - **t27, all three model configurations:** the fallback no longer turns the model's abstention into a wrong test regression. It is a missed abstention again (the log states a missing Neo4j database in wording Kensa does not recognise).
  - **t58, LLM + full text:** the fallback no longer rescues a correct test regression. The model's own answer, `docker` (`conflicting`), is reported instead, so this case is lost. This is D-046's measured cost on this split.
- **The other wrong `plausible` test regressions remain** (t16 and t47 in every configuration, and the hybrid configuration's t48): they are now shown as hypotheses, not as corroborated causes.

## Cost
- **A real test regression is never shown as `corroborated`.** The UI now shows one as "Plausible, not confirmed" and tells the reader to treat it as a hypothesis, even when the assertion is the whole story. Its explanation already names a failing test as an example of a symptom, so no UI text changed. On v2 dev, test regressions are 7 of the 60 cases; on the test split 3–4 correct ones per configuration moved to `plausible`.
- **The fallback rescues fewer answers:** it rescued a correct test regression from a model that was misled by a lookalike log. That no longer happens: d58 on dev and t58 on the spent test split, each in LLM + full text. Both are lookalike cases, built to look like an environmental failure.
- **What it buys:** on the spent test split, the 3 fallback answers that were wrong (t27) are gone, and every `corroborated` answer is right. On dev, no wrong answer was `corroborated` before or after.
- **Test regressions no longer feed the incident index,** so retrieval cannot surface a past test regression as a precedent.

## Limitations
- **No held-out measurement.** The dev split was used to develop M5.1's patterns, and the test split exposed the flaw that D-046 fixes. The rule was chosen after seeing both, so neither can say how it does on new failures.
- **Run-to-run variation is real.** Between the two dev runs, where D-046 cannot reach, it:
  - changed two answers' categories: d51 in LLM + full text, and d58 in agent + full text
  - changed one answer's status: d50
  - produced three different first attempts in agent + full text

  Differences of one or two cases are within it. M5.1's last dev run was stored in `kensa_eval`, which the harness empties per run and the held-out run then reused. So its attempts are inferred from its JSON-lines rows, not read from its events.
- **The remaining failure modes stay:**
  - Causes stated in wording the patterns don't know are still missed (t16 and t27 on test). They are now reported as `plausible` or as an abstention, not `corroborated`.
  - A lookalike log can still mislead the model (d58, t58). The answer is then flagged as `conflicting`, not hidden.
- **Same data limits as M5.1:** 60 synthetic cases per split from one independent author. The category is the proxy for the root cause.

## What would measure it
A small new held-out set (v3), written by a separate LLM author like v1 and v2, frozen before any run, and run once under a protocol fixed beforehand. It would measure:
- how often `corroborated` is right on new failures
- how often test regressions are found, and whether the fallback's lost rescues matter

This needs the owner's decision. Nothing has been tuned on the v2 test split, and it stays spent.
