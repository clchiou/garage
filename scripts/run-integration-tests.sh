#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

goto() {
  local -r PROJECT_DIR="${1}"
  ensure_directory "${PROJECT_DIR}"
  cd "${PROJECT_DIR}"
  show "${2:-INTEGRATION TEST}: ${PROJECT_DIR}"
}

goto "${ROOT}/py/ops"
scripts/run-itests.sh ops-tester
