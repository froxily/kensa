# Docker build, pull and daemon failures

## Symptoms
- `failed to solve:` from BuildKit, often followed by the failing Dockerfile instruction and its exit code.
- `pull access denied`, `manifest unknown`, or `manifest for image:tag not found`: the image or tag does not exist, or authentication is missing.
- `Cannot connect to the Docker daemon` on runners or containers without Docker.
- `COPY failed: file not found in build context` or `"/x": not found`.
- `exec format error`: wrong CPU architecture for the base image.

## Where to look
- The Dockerfile at the failing commit: `FROM` tags, `COPY` paths relative to the build context, `RUN` commands.
- The workflow's `docker/build-push-action` or `docker build` context and `file:` arguments.
- `.dockerignore`, which can exclude files that `COPY` needs.
- Registry login steps and the credentials they use.

## Common causes
- A base image tag that was removed or mistyped (for example a version that was never published).
- A build context that does not contain the files the Dockerfile copies.
- A `RUN` step that fails because of a dependency or network issue inside the build.
- A missing registry login step for a private registry.

## Safe fixes
- Pin a base image tag that exists, ideally by digest.
- Make the build context and the `COPY` paths agree, and check `.dockerignore`.
