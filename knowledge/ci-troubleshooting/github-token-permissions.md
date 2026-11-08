# GitHub token permissions

## Symptoms
- `Resource not accessible by integration` (HTTP 403) from the GitHub API.
- `remote: Permission to org/repo.git denied to github-actions[bot]` when pushing.
- Failing to create releases, comment on pull requests, push tags, publish packages or upload SARIF.
- `Bad credentials` or 401 when a personal token has expired or was revoked.

## Where to look
- The workflow or job `permissions:` block. If any permission is set, every unlisted permission becomes `none`.
- The repository or organisation default for `GITHUB_TOKEN` (read-only by default in many organisations).
- The event that triggered the run: `pull_request` runs from forks get a read-only token.
- Which token the step uses: `GITHUB_TOKEN` versus a personal access token or app token.

## Common causes
- A job pushes, tags or releases while `contents: read` (or no write permission) is in effect.
- `pull-requests: write` or `issues: write` is missing for commenting actions.
- `packages: write` is missing for publishing to GitHub Packages.
- `id-token: write` is missing for OIDC cloud authentication.

## Safe fixes
- Grant the narrowest permission needed, at job level, for the job that needs it.
- Do not switch to `permissions: write-all` or broad personal tokens to make the error go away.
