#!/bin/bash

# Build application pods (run multiple builders).

set -o errexit -o nounset -o pipefail

main() {
  if [[ -z "${1:-}" ]]; then
    echo "Usage: $(basename "${0}") {echod|httpd} --builder BUILDER --preserve-container --output OUTPUT ..."
    exit 1
  fi

  local VERSION="${VERSION:-$(date +%s)}"

  local BUILDER_ARGS=(build)
  local RULES=()
  if [[ "${1}" = "echod" ]]; then
    BUILDER_ARGS+=(\
      --parameter "//py/garage/examples/echod:version/echod=${VERSION}"
    )
    RULES+=(\
      //py/garage/examples/echod:build_pod/echod/echod
      //py/garage/examples/echod:build_pod/echod
    )
  elif [[ "${1}" = "httpd" ]]; then
    BUILDER_ARGS+=(\
      --parameter "//py/cpython/httpd:version/httpd=${VERSION}"
    )
    RULES+=(\
      //py/cpython/httpd:build_pod/httpd/httpd
      //py/cpython/httpd:build_pod/httpd
    )
  else
    echo "unknown application pod: ${1}"
    exit 1
  fi

  shift

  local BUILDER="$(realpath "$(dirname "${BASH_SOURCE}")/builder")"
  if [[ ! -x "${BUILDER}" ]]; then
    echo "not executable: ${BUILDER}"
    exit 1
  fi

  local rule
  for rule in "${RULES[@]}"; do
    (set -o xtrace; "${BUILDER}" "${BUILDER_ARGS[@]}" "${rule}" "${@}")
  done
}

main "${@}"
