# Missing environment variables and secrets

## Symptoms
- Messages such as "environment variable X is not set", "X is undefined", `KeyError: 'X'` (Python `os.environ[...]`), `Error: Missing required ...`, or a config loader reporting a missing key.
- Frontend builds (Vite, Next.js, CRA) that embed variables at build time fail in a pre-build check, or produce a bundle that calls `undefined/api`.
- A step that worked locally fails only in CI, because the local shell or a `.env` file supplied the value.

## Where to look
- The workflow `env:` blocks, at workflow, job and step level. Variables set in one job are not visible in another.
- `${{ secrets.NAME }}` and `${{ vars.NAME }}` references. A secret that does not exist evaluates to an empty string, without an error.
- `.env.example` or settings documentation, for the list of required names.
- Environments with protection rules: secrets scoped to an environment are only available to jobs that declare `environment:`.

## Common causes
- The variable was added to the code but never to the workflow.
- The secret name differs in case or spelling from the reference.
- The run comes from a fork: pull requests from forks do not receive repository secrets.
- A variable is exported in one `run:` step but read in a later step; each step is a new shell. Use `$GITHUB_ENV` to pass it on.

## Safe fixes
- Add the variable to the job's `env:`, from `secrets`/`vars` if it is sensitive.
- Never print secret values to the log to debug them; check whether they are empty instead.
