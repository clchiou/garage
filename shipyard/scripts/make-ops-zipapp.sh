#!/bin/bash

# Bundle together ops tool and its dependencies in one zip app (using
# this script is easier than doing it in a builder).

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ "${#}" -lt 1 ]]; then
  show "usage: ${PROG} OUTPUT"
  exit 1
fi

readonly OUTPUT="$(realpath "${1}")"

set -o xtrace

# ops
pushd "${ROOT}/py/ops"
python3 setup.py build bdist_zipapp --output "${OUTPUT}"
popd

# garage
pushd "${ROOT}/py/garage"
python3 setup.py build bdist_zipapp --output "${OUTPUT}"
popd

# startup
pushd "${ROOT}/py/startup"
# NOTE: startup/setup.py does not support bdist_zipapp
zip --grow -r "${OUTPUT}" startup.py
popd
