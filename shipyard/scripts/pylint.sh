#!/bin/bash

# Simple wrapper of pylint.

set -o errexit -o nounset -o pipefail

main() {
  local ROOT="$(realpath "$(dirname "${BASH_SOURCE}")/../..")"
  local MORE_PYTHONPATH="${ROOT}/py/foreman:${ROOT}/shipyard/lib"

  export PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${MORE_PYTHONPATH}"
  echo "export PYTHONPATH=${PYTHONPATH}"

  set -o xtrace
  pylint "${@}"
}

main "${@}"
