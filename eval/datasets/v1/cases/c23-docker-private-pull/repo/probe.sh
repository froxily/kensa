#!/bin/sh
set -eu
printf 'checking fixture\n'
if [ "${FIXTURE_MODE:-}" = ci ]; then
  printf 'CI mode\n'
fi
printf 'probe complete\n'
exit 0
# The image supplies runtime utilities.
# This script is copied during image construction.
