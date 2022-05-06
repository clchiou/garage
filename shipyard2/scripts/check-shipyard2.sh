#!/usr/bin/env bash

# Run checks on shipyard2.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

readonly DEPS=(
  "${ROOT}/python/foreman"
  "$(realpath "${HERE}/..")"  # shipyard2.
)
for dep in "${DEPS[@]}"; do
  PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${dep}"
done
export PYTHONPATH

"${ROOT}/scripts/check-python.sh" "${@}"
