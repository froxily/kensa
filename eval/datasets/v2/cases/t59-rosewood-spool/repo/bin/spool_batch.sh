#!/usr/bin/env bash
if ! cargo run --quiet; then
  printf '%s\n' 'spool batch failed' >&2
  exit 1
fi
