#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

which python3 > /dev/null || abort "python3 is unavailable"

# Make build.py dependencies available (even inside builder pod).
readonly DEPS=(
  "$(realpath "${HERE}/..")"  # shipyard2.
  "${ROOT}/python/g1/bases"
  "${ROOT}/python/g1/containers"
  "${ROOT}/python/g1/operations/cores"
  "${ROOT}/python/g1/scripts"
)
for dep in "${DEPS[@]}"; do
  PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${dep}"
done
export PYTHONPATH

exec "${ROOT}/python/foreman/foreman.py" "${@}"
