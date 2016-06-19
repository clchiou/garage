#!/bin/bash

# Shorthand for building httpd; sample arguments:
#   ./scripts/do-build-httpd.sh --builder BUILDER --output OUTPUT

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
    //cpython/examples/httpd:build_image \
    //cpython/examples/httpd:build_configs \
    --parameter "//cpython/examples/httpd:version=${VERSION}" \
    "${@}"
}

main "${@}"
