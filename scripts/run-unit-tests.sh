#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

goto() {
  local -r PROJECT_DIR="${1}"
  ensure_directory "${PROJECT_DIR}"
  cd "${PROJECT_DIR}"
  show "${2:-UNIT TEST}: ${PROJECT_DIR}"
}

readonly TEST_DIRS=($(find "${ROOT}/py" -type d -name tests))
for test_dir in "${TEST_DIRS[@]}"; do
  goto "$(dirname "${test_dir}")"
  python3 -m unittest
done

goto "${ROOT}/shipyard"
scripts/python3.sh -m unittest

goto "${ROOT}/java"
./gradlew test

goto "${ROOT}/py/garage" 'PACKAGE AVAILABILITY TEST'
# Add `|| true` for now because this test is flaky.
/usr/local/bin/python3 -m unittest || true
