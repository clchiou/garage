#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

readonly DEPS=(
  "$(realpath "${HERE}/..")"  # shipyard2.
  "${ROOT}/py/foreman"
)
for dep in "${DEPS[@]}"; do
  PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${dep}"
done
export PYTHONPATH

exec python3 -m shipyard2.releases "${@}"
