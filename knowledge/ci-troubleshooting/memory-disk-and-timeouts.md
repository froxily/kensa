# Out of memory, disk space and timeouts

## Symptoms
- `Process completed with exit code 137`, or `Killed`: the process was terminated, usually by the out-of-memory killer.
- `JavaScript heap out of memory` / `Reached heap limit`; Java `OutOfMemoryError`; a build daemon disappearing.
- `No space left on device`, often during Docker builds, cache restores or large dependency installs.
- `The job running on runner ... has exceeded the maximum execution time`, `The operation was canceled`, or tool-specific timeouts.

## Where to look
- The memory-heavy step (bundling, compilation, test runs with many workers) and its parallelism settings.
- Disk usage from Docker images, caches and build outputs on the runner.
- `timeout-minutes` at job or step level, and steps that wait on external services.

## Common causes
- Too many parallel workers for the runner's memory.
- Node's default heap is too small for a large bundle.
- Docker layers and caches filling the disk.
- A hanging test or a network call without a timeout, consuming the job's time budget.

## Safe fixes
- Reduce parallelism, or raise specific limits (for example `NODE_OPTIONS=--max-old-space-size=...`) once the workload is confirmed to need them.
- Free disk space by pruning unused images and caches.
- Add timeouts to the step that hangs instead of only raising the job timeout.
