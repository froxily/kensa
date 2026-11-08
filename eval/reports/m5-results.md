# M5 results: held-out evaluation, latency and what they mean

> 2026-10-30. The system was frozen at `bd6a252` before the first and only run of the held-out test split, under the protocol committed beforehand (`m5-protocol.md`, D-037). Generated tables: `m5-evaluation.md`, `m5-diagnosis-test.md`, `m5-diagnosis-dev.md`. Raw rows: `m5-diagnosis-{test,dev}.jsonl`. GPU samples: `m5-gpu-samples.csv`, `m5-gpu-throttle.csv`. Nothing was tuned on the test answers.

## Headline
- **Held-out accuracy is 11–13 of 20 for every configuration.** That is well below the dev split (14–20 of 20), where the M3 agent with hybrid retrieval scored 20/20 and scores 12/20 on held-out.
- **On held-out, neither retrieval nor the agent shows a measurable gain.** The LLM adds 1–2 cases over the rules. With 20 cases, every 95% interval overlaps: 12/20 is 0.39–0.78, 13/20 is 0.43–0.82.
- **Every citation Kensa accepted is genuine.** An independent re-check found all 400 accepted citations in the test run on their cited line.
- **Grounding does not establish the cause.** Every wrong held-out answer (33 across the six configurations) cites genuine lines from its own log. Most are presented with high confidence: 29 of the 33 have confidence ≥ 0.5.
- **"Verified" did not transfer.** On dev, every verified answer was correct. On held-out, 57–78% were correct for the LLM configurations and 69% for rules only.

## Held-out test split (20 cases)

| configuration | correct | wrong | abstained correctly / missed | insufficient detected | false confidence | grounded but wrong (verified) | verified answers correct |
|---|---|---|---|---|---|---|---|
| rules only (M3 agent) | 11 | 4 | 2 / 5 | 2/2 | 4 | 4 (4) | 9/13 |
| LLM, no retrieval (log tail) | 12 | 7 | 1 / 1 | 1/2 | 6 | 7 (4) | 6/10 |
| LLM + full text | 13 | 5 | 1 / 2 | 1/2 | 4 | 5 (2) | 4/6 |
| LLM + hybrid (M2) | 13 | 5 | 2 / 2 | 2/2 | 4 | 5 (2) | 7/9 |
| agent + full text (M3) | 12 | 6 | 1 / 2 | 1/2 | 6 | 6 (3) | 4/7 |
| agent + hybrid (M3, production) | 12 | 6 | 2 / 2 | 2/2 | 6 | 6 (3) | 7/10 |

Definitions are in `m5-protocol.md`:
- **False confidence:** wrong, and presented as established (verified or supported).
- **Grounded but wrong:** wrong, with an accepted citation from the run's own log. For the test split this was checked in the database.

**Citation validity** (accepted over generated, final answer):
- **LLM configurations:** 92–99%.
- **Rules only:** 18/18.
- **Agent, across all attempts:** 92/98 and 91/92.

Rejected citations are never shown as evidence.

## Dev versus held-out (same frozen commit)

| configuration | dev | held-out |
|---|---|---|
| rules only | 15 | 11 |
| LLM, no retrieval | 14 | 12 |
| LLM + full text | 15 | 13 |
| LLM + hybrid (M2) | 18 | 13 |
| agent + full text (M3) | 16 | 12 |
| agent + hybrid (M3) | 20 | 12 |

The dev split was used throughout M2–M4 to develop prompts, rules, retrieval and the verifier. The configurations that were iterated on the most lost the most (agent + hybrid: −8). The dev gains of hybrid retrieval and the agent (+3 to +5 cases) did not appear on held-out (0 to −1). The honest reading: those gains were largely fitted to the dev cases.

## Why answers were wrong (hand review after the run, for reporting only)

Every configuration got five cases wrong or missed them: c03, c04, c10, c13 and c27. Three patterns account for most errors.

1. **Surface category instead of cause** (c03, c04, c13, c18). The cause is a missing variable, a missing permission or an unpublished port, but it reaches the log through a test runner or a Docker build. The log line shows the true cause: "SERVICE_REGION must be set" in c04, "denied: permission_denied: write_package" in c13, "connection refused" in c18. But the surrounding `--- FAIL:` / `failed to solve` lines win.
   - In c04, c13 and c18 the rule classifier makes the same choice, the models agree, and agreement makes the answer **verified** with 0.90–0.98 confidence.
   - In c03 the rules abstain and every model answers `test_regression` (supported, 0.70).
   - This is the limitation seen in M4's live run (D-029: verified means grounded and rule-consistent, not causally right), now measured.
2. **A misleading symptom** (c10). An authentication error hides a missing `DB_USER`. The configurations split between `test_regression` and `db_connectivity`, and none found the variable.
3. **Missed diagnoses** (c24, c27, c37). The models abstained on a Docker stage failure, a solution-path error and a heap limit: correct causes the 4B model did not commit to. These are safe failures (cause shown as not established), but failures.

For insufficient evidence, c40 (a generic smoke-test failure) was answered `test_regression` (supported) by three configurations: LLM without retrieval, LLM + full text, and agent + full text. Both hybrid configurations and rules only abstained correctly.

**Not established:** whether the model follows the rule hint (anchoring) or reaches the same reading independently. Testing that needs an ablation, which must not be run on this test split. It is the first question for v2.

## What these results do and do not show
- **They show:**
  - accepted citations are genuine
  - abstention works on clear no-failure logs
  - the safety properties hold (nothing is applied, unsafe edits are dropped)
- **They do not show** that Kensa finds the right root cause on new cases at a useful rate, or that its "verified" label means "correct".
- **The data:** 20 synthetic cases per split, written by one separate LLM author. Differences of 1–2 cases are noise.
- **Remediation:** fix-keyword hits (12–16/20 for the LLM configurations) are a weak proxy, not a correctness measure. Diffs are mechanically checked only and are never claimed to be semantically correct or safe.

## Latency

| | dev run (14:19–15:01 UTC) | held-out run (15:01–15:32 UTC) |
|---|---|---|
| diagnosis call p50 | 20.2 s | 13.3 s |
| generation speed p50 | 22 tokens/s | 42 tokens/s |
| output tokens p50 | 354 | 364 |
| model reload (p50, share of diagnosis calls) | 5.3 s, 58/99 | 4.4 s, 60/108 |
| GPU busy-sample median clock | 480 MHz | 1,237 MHz |
| GPU power limit during busy samples | 30 W in 39/39 (logged from 14:35 UTC) | 30 W in 0/39 (60 or 95 W) |

Wall time per case (p50 / p95):

| configuration | held-out | dev |
|---|---|---|
| LLM + full text | 10.2 / 12.3 s | 15.7 / 23.4 s |
| LLM + hybrid | 21.3 / 24.0 s | 29.3 / 35.3 s |
| agent + hybrid | 23.6 / 39.9 s | 32.0 / 58.3 s |
| rules only | 0.3 / 0.5 s | 0.3 / 0.5 s |

- **The dev/held-out latency difference is environmental:** same commit, same output length.
  - During the dev run the GPU hit its 87 °C target. The driver held its power limit at 30 W (default 60 W), with "SW Thermal Slowdown" and "SW Power Cap" active, and generation ran at half speed.
  - The limit returned to 60–95 W during the held-out run.
  - The same throttling is a likely explanation for the 29 s M3 figure in D-038, but GPU state was not recorded during M3. What triggers the cap (the laptop's power mode, mains or battery, cooling) was not determined.
- **Hybrid retrieval roughly doubles wall time over full text.**
  - **Cause:** the embedder (~3.6 s load, in 59 of 103 embedding calls) and the LLM (~4.4 s reload) swap on the 4 GB GPU. The embedding itself takes milliseconds.
  - **Alternatives:**
    - running the embedder on the CPU is slower: 0.8 chunks/s, D-024
    - both models together do not fit in VRAM
  - On held-out, hybrid was not more accurate than full text (13 vs 13; 12 vs 12).
  - Changing the default on that evidence would be tuning on the test split, so it is a v2 question, not an M5 change.
- **No code optimisation was justified.** The two costs are model swapping (a hardware limit with no faster measured alternative) and thermal throttling (environmental).

## Proposed next step: evaluation set v2 (not started)
- **Authoring:** a new, independently written set, with its own frozen dev/test split, written before any Kensa change is evaluated on it. It should have more cases (≥ 60 per split, so 5-point differences become meaningful), with real logs where licensing allows.
- **Deliberate coverage of the failure patterns above:** causes that surface through test runners and Docker builds, misleading symptoms, and empty secrets.
- **First experiments on its dev split:**
  - LLM without the rule hint (anchoring)
  - a "cause behind the surface" rule set
  - "verified" requiring evidence beyond category agreement
  - full text versus hybrid as the default
- **This test split is now spent.** Re-running v1 test after any change is not a valid held-out result.
