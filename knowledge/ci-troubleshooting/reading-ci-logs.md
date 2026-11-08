# Reading a failed CI log

1. **Find the failing step.** GitHub Actions marks it with `##[error]Process completed with exit code N`. The cause is almost always above that line, inside the same `##[group]`.
2. **Find the first real error, not the last.** Later errors are often consequences: a failed install produces missing-module errors, and a missing database produces dozens of test errors.
3. **Separate symptoms from causes.** Ask what would have to be true for the first error to happen, and look for evidence of it in the workflow file and the repository at the failing commit.
4. **Check what changed.** Recent edits to the workflow, the manifests or lockfiles, and the Dockerfile explain most new failures.
5. **Know when evidence is insufficient.** If the log is truncated, or only shows a generic exit code, the honest conclusion is that the cause is not established. Name what additional evidence is needed (full log, the workflow file, the failing step with debug logging enabled).
6. **Exit codes:** 1 is a generic failure; 2 is often a usage error; 126/127 mean not executable / command not found; 137 means killed (often out of memory); 143 means terminated (often cancellation or timeout).
