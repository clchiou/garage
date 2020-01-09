#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

[[ -n "${SHIPYARD2_PARAMS_PATH:-}" ]] || abort "expect SHIPYARD2_PARAMS_PATH"
ensure_file "${SHIPYARD2_PARAMS_PATH}"

export PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${ROOT}/py/foreman"

exec python3 -m shipyard2.releases \
  --parameter-file "${SHIPYARD2_PARAMS_PATH#*.}" "${SHIPYARD2_PARAMS_PATH}" \
  "${@}"
