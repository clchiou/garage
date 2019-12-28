#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# XXX Because sudo does not find venv python3, as a workaround, we
# export all of build's dependencies (we could make sudo find venv
# python3, but I think it is better to let sudo find distro python3).
readonly DEPS=(
  "${ROOT}/py/foreman"
  "${ROOT}/py/g1/apps"
  "${ROOT}/py/g1/bases"
  "${ROOT}/py/g1/containers"
  "${ROOT}/py/startup"
)
for dep in "${DEPS[@]}"; do
  PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${dep}"
done
export PYTHONPATH

readonly BUILD="$(realpath "${HERE}/../shipyard2/build.py")"

exec sudo --preserve-env=PYTHONPATH python3 "${BUILD}" "${@}"
