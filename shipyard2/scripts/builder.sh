#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# XXX We require BUILDER_PARAMS_PATH to work around this issue:
# builder and ctr need the same set of parameters to work together
# correctly.  We decide to use a common parameter file since passing
# around `--parameter` command-line flags is not quite maintainable.
[[ -n "${BUILDER_PARAMS_PATH:-}" ]] || abort "expect BUILDER_PARAMS_PATH"
ensure_file "${BUILDER_PARAMS_PATH}"

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

# XXX Preserve BUILDER_PARAMS_PATH because builder calls ctr.
exec sudo --preserve-env=BUILDER_PARAMS_PATH,PYTHONPATH \
  python3 -m shipyard2.builders \
  --parameter-file "${BUILDER_PARAMS_PATH#*.}" "${BUILDER_PARAMS_PATH}" \
  "${@}"
