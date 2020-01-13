#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

readonly DEPS=(
  "$(realpath "${HERE}/..")"  # shipyard2.
  "${ROOT}/py/foreman"
  "${ROOT}/py/g1/bases"
  "${ROOT}/py/g1/scripts"
  "${ROOT}/py/startup"
)
for dep in "${DEPS[@]}"; do
  PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${dep}"
done
export PYTHONPATH

exec python3 -m shipyard2.releases "${@}"
