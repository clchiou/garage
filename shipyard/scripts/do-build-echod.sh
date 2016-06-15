#!/bin/bash

# Shorthand for building echod; sample arguments:
#   ./scripts/do-build-echod.sh --builder BUILDER --out OUT

set -o errexit -o nounset -o pipefail

main() {
  local BUILDER="$(realpath "$(dirname "${BASH_SOURCE}")/builder")"
  if [[ ! -x "${BUILDER}" ]]; then
    echo "not executable: ${BUILDER}"
    exit 1
  fi

  local VERSION="${VERSION:-$(date +%s)}"

  set -o xtrace

  "${BUILDER}" build \
    //garage/examples/echod:build_image \
    //garage/examples/echod:build_configs \
    --parameter "//garage/examples/echod:version=${VERSION}" \
    "${@}"
}

main "${@}"
