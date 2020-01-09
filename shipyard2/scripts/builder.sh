#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# XXX We require CTR_PARAMS_PATH to work around this issue: builder and
# ctr need the same set of parameters (because we make builder import
# g1.containers codes).  We decide to use a common parameter file since
# tossing around `--parameter` command-line flags is not maintainable.
[[ -n "${CTR_PARAMS_PATH:-}" ]] || abort "expect CTR_PARAMS_PATH"
ensure_file "${CTR_PARAMS_PATH}"

# XXX Because sudo does not find venv python3, as a workaround, we
# export all of builder's dependencies (we could make sudo find venv
# python3, but I think it is better to let sudo find distro python3).
readonly DEPS=(
  "$(realpath "${HERE}/..")"  # shipyard2.
  "${ROOT}/py/foreman"
  "${ROOT}/py/g1/apps"
  "${ROOT}/py/g1/bases"
  "${ROOT}/py/g1/containers"
  "${ROOT}/py/g1/scripts"
  "${ROOT}/py/startup"
)
for dep in "${DEPS[@]}"; do
  PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${dep}"
done
export PYTHONPATH

# XXX Preserve CTR_PARAMS_PATH because builder does not just import
# g1.containers, but also subprocess ctr.
exec sudo --preserve-env=CTR_PARAMS_PATH,PYTHONPATH \
  python3 -m shipyard2.builders \
  --parameter-file "${CTR_PARAMS_PATH#*.}" "${CTR_PARAMS_PATH}" \
  "${@}"
