#!/bin/bash

# Bundle together ops tool and its dependencies in one zip app (using
# this script is easier than doing it in a builder).

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ "${#}" -lt 1 ]]; then
  show "usage: ${PROG} [PYTHON3] OUTPUT"
  exit 1
fi

# Add buildtools to PYTHONPATH
export PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${ROOT}/py/buildtools"

if [[ "${#}" -gt 1 ]]; then
  readonly PYTHON3="${1}"
  shift
fi

readonly OUTPUT="$(realpath "${1}")"

set -o xtrace

rm -f "${OUTPUT}"

# ops
pushd "${ROOT}/py/ops"
rm -rf build  # Clean up any previous build
"${PYTHON3:-python3}" setup.py build bdist_zipapp --output "${OUTPUT}"
rm -rf build
popd

# garage
pushd "${ROOT}/py/garage"
rm -rf build  # Clean up any previous build
"${PYTHON3:-python3}" setup.py build bdist_zipapp --output "${OUTPUT}"
rm -rf build
popd

# startup
pushd "${ROOT}/py/startup"
# startup/setup.py does not support bdist_zipapp at the moment
zip --grow -r "${OUTPUT}" startup.py
popd
