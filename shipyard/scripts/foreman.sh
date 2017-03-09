#!/bin/bash

# Set up environment for foreman.py

source "$(dirname "${BASH_SOURCE}")/common.sh"

# Make sure our --path is the first.
readonly COMMAND="${1}"
shift
set -o xtrace
exec "${ROOT}/py/foreman/foreman.py" "${COMMAND}" --path "${ROOT}/shipyard/rules" "${@}"
