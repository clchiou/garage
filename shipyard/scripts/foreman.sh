#!/bin/bash

# Set up environment for foreman.py

source "$(dirname "${BASH_SOURCE}")/common.sh"

if ! which python3 > /dev/null; then
  echo "$(basename "${BASH_SOURCE}"): install python3" 2>&1
  sudo apt-get update
  sudo apt-get install --yes python3
fi

# Make sure our --path is the first.
readonly COMMAND="${1:-}"

if [ -z "${COMMAND}" ]; then
  set -o xtrace
  exec "${ROOT}/py/foreman/foreman.py" "${@}"
fi

shift

set -o xtrace
exec "${ROOT}/py/foreman/foreman.py" "${COMMAND}" --path "${ROOT}/shipyard/rules" "${@}"
