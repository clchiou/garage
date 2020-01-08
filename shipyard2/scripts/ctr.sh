#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# XXX We require BUILDER_PARAMS_PATH to work around this issue:
# builder and ctr need the same set of parameters to work together
# correctly.  We decide to use a common parameter file since passing
# around `--parameter` command-line flags is not quite maintainable.
[[ -n "${BUILDER_PARAMS_PATH:-}" ]] || abort "expect BUILDER_PARAMS_PATH"
ensure_file "${BUILDER_PARAMS_PATH}"

# XXX Because sudo does not find venv python3, as a workaround, we
# export all of ctr's dependencies (we could make sudo find venv
# python3, but I think it is better to let sudo find distro python3).
readonly DEPS=(
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

exec sudo --preserve-env=PYTHONPATH \
  python3 -m g1.containers \
  --parameter-file "${BUILDER_PARAMS_PATH#*.}" "${BUILDER_PARAMS_PATH}" \
  "${@}"
