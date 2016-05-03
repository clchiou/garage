#!/bin/bash

# Simple wrapper for calling foreman.py.

set -o errexit -o nounset -o pipefail

main() {
  if ! which python3 > /dev/null; then
    echo "Install Python 3"
    sudo apt-get install --yes python3
  fi

  local ROOT="$(realpath "$(dirname "${BASH_SOURCE}")/../..")"
  local SHIPYARD="${ROOT}/shipyard"
  local FOREMAN="${ROOT}/py/foreman/foreman.py"

  # With this `import shipyard` will import shipyard/shipyard.py.
  export PYTHONPATH="${SHIPYARD}"

  exec "${FOREMAN}" "${@}"
}

main "${@}"
