# Test regressions

## Symptoms
- pytest: `FAILED tests/x.py::test_y - AssertionError`, a summary line such as `== 3 failed, 120 passed ==`.
- Jest/Vitest: `Tests: 2 failed`, `expect(received).toBe(expected)` diffs.
- JUnit/Maven Surefire: `Tests run: 40, Failures: 2`. Go: `--- FAIL: TestX`. Rust: `test result: FAILED`.

## How to read them
- Distinguish failures (an assertion did not hold) from errors (setup crashed). Many errors in setup usually point at infrastructure (database, network, missing files), not at the code under test.
- Compare the expected and actual values in the assertion diff: an off-by-one, a changed default or a renamed field usually points straight at the change.
- Check whether the same tests fail consistently or intermittently (flaky tests depend on timing, ordering or external services).

## Where to look
- The source file that implements the asserted behaviour, and the test file, at the failing commit.
- Recent changes to shared fixtures, test data or configuration.

## Common causes
- A behaviour change in the code that the tests did not anticipate, or a test that was not updated for an intended change.
- Time zone, locale or ordering assumptions that differ on CI runners.

## Safe fixes
- Fix the code, or update the test only when the new behaviour is intended. Do not skip or delete failing tests to make CI green.
