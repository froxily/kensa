# Lichen probe

A small container for checking service startup.

## Build

Run `docker build -t lichen-probe .` from the repository root.

## Run

Run `docker run --rm lichen-probe` to print the readiness message.

## Development

The entry point is in `cmd/lichen`.
Use a recent Go toolchain for local builds.
