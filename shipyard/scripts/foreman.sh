#!/bin/bash

# Simple wrapper for calling foreman.py.

set -o errexit -o nounset -o pipefail

main() {
  # ROOT is /path/to/garage.
  local ROOT="$(realpath "$(dirname "${BASH_SOURCE}")/../..")"
  if [[ ! -d "${ROOT}/.git" ]]; then
    echo "not git repo: ${ROOT}" 1>&2
    exit 1
  fi

  local SHIPYARD="${ROOT}/shipyard"
  local FOREMAN="${ROOT}/py/foreman/foreman.py"

  # With this `import shipyard` will import lib/shipyard.py.
  export PYTHONPATH="${SHIPYARD}/lib${PYTHONPATH:+:}${PYTHONPATH:-}"
  echo "export PYTHONPATH=${PYTHONPATH}" 1>&2

  # Make sure our --path is the first.
  local COMMAND="${1}"
  shift

  set -o xtrace
  exec "${FOREMAN}" "${COMMAND}" --path "${SHIPYARD}/shipyard" "${@}"
}

main "${@}"
