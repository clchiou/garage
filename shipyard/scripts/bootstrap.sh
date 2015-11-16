#!/bin/bash

set -o errexit -o nounset -o pipefail

main() {
  if [[ -z "${1:-}" ]]; then
    echo "Usage: $(basename ${0}) TAG"
    exit 1
  fi

  local TAG="${1}"
  local BOOTSTRAP="$(fullpath "$(dirname ${0})/../bootstrap")"

  set -o xtrace
  docker build --tag "${TAG}" "${BOOTSTRAP}"
}

fullpath() {
  cd "${1}"; pwd; cd - > /dev/null
}

main $@
