# Workflow paths and missing files

## Symptoms
- `No such file or directory`, `ENOENT`, "Could not open requirements file".
- `Can't find 'action.yml'` or "Unable to resolve action" for a local or remote action.
- Artifact upload: "No files were found with the provided path".
- `working-directory` that does not exist, or a script invoked with the wrong relative path.
- "module not found" or "cannot find package" errors that are really caused by running in the wrong directory.

## Where to look
- The paths referenced in the workflow (`run:` commands, `working-directory`, `with: path:`, `uses: ./.github/actions/...`) compared with the repository tree at that commit.
- Recent renames or moves of directories and files.
- Monorepo layouts, where each package needs its own working directory.
- Whether the checkout step ran before the step, and with which `path:`.

## Common causes
- A file was renamed or moved but the workflow was not updated.
- A wrong `working-directory`, or a missing `cd`.
- Artifacts uploaded from a path that the build never produced.
- Case-sensitivity: Linux runners distinguish `Docs/` from `docs/`.

## Safe fixes
- Update the workflow path to match the repository, or restore the expected file. Verify against the tree at the failing commit.
