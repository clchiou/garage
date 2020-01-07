#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

which python3 > /dev/null || abort "python3 is unavailable"

# Make build.py dependencies available (even inside builder pod).
readonly DEPS=(
  "$(realpath "${HERE}/..")"  # shipyard2.
  "${ROOT}/py/g1/bases"
  "${ROOT}/py/g1/containers"
  "${ROOT}/py/g1/scripts"
)
for dep in "${DEPS[@]}"; do
  PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${dep}"
done
export PYTHONPATH

# Put our `--path` before ${@:2} so that it is the first one.
exec "${ROOT}/py/foreman/foreman.py" \
  ${1:-} \
  --path "$(realpath "${HERE}/../rules")" \
  "${@:2}"
