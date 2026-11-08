# Dependency resolution and build failures

## Symptoms
- npm: `ERESOLVE unable to resolve dependency tree`, peer-dependency conflicts, `npm ci` complaining that `package-lock.json` is out of sync with `package.json`.
- pnpm/yarn: frozen-lockfile errors ("lockfile needs updates", outdated lockfile).
- Python: `ResolutionImpossible`, "No matching distribution found", `ModuleNotFoundError` at import time, wheels unavailable for the runner's Python version.
- JVM: Maven "Could not resolve dependencies", Gradle "Could not resolve all files for configuration".
- Compilers: TypeScript `error TSxxxx`, Rust "could not compile", Go "undefined:" or module checksum mismatches.

## Where to look
- The manifest and lockfile at the failing commit: version ranges, recently bumped packages.
- The toolchain version the workflow installs (`setup-node`, `setup-python`, `setup-java` versions) compared with what the project expects (`engines`, `requires-python`, toolchain files).
- Caches restored with a key that no longer matches the lockfile.

## Common causes
- A dependency upgrade introduced an incompatible peer or transitive requirement.
- The lockfile was not regenerated after editing the manifest.
- The CI toolchain version differs from local development.
- A package was removed from or renamed in the registry, or is a private package that needs a token.

## Safe fixes
- Pin or upgrade to compatible versions and regenerate the lockfile.
- Align the toolchain version in the workflow with the project's declared version.
- Avoid forcing resolution (`--force`, `--legacy-peer-deps`) as a permanent fix: it hides real incompatibilities.
