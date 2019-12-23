#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

which python3 > /dev/null || abort "python3 is unavailable"

ARGS=(
  ${1:-}
  # Make sure our `--path` is the first one.
  --path "$(realpath "${HERE}/../rules")"
  "${@:2}"
)

exec "${ROOT}/py/foreman/foreman.py" "${ARGS[@]}"
