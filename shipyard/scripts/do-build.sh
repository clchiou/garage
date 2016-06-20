#!/bin/bash

# Handy shortcuts for launching builder.

set -o errexit -o nounset -o pipefail

main() {
  if [[ -z "${1:-}" ]]; then
    echo "Usage: $(basename "${0}") {all|echod|httpd} --builder BUILDER --output OUTPUT ..."
    exit 1
  fi

  local VERSION="${VERSION:-$(date +%s)}"

  local BUILDER_ARGS=(build)
  if [[ "${1}" = "all" ]]; then
    # Enumerate all packages here.
    BUILDER_ARGS+=(
      //cpython:build
      //garage:build
      //http2:build
      //lxml:build
      //mako:build
      //nanomsg:build
      //nanomsg/py:build
      //nghttp2:build
      //pyyaml:build
      //requests:build
      //sqlalchemy:build
      //startup:build
      //v8:build
      //v8/py:build
    )
  elif [[ "${1}" = "echod" ]]; then
    BUILDER_ARGS+=(
      //garage/examples/echod:build_pod
      --parameter "//garage/examples/echod:version=${VERSION}"
    )
  elif [[ "${1}" = "httpd" ]]; then
    BUILDER_ARGS+=(
      //cpython/examples/httpd:build_pod
      --parameter "//cpython/examples/httpd:version=${VERSION}"
    )
  else
    echo "unknown build target: ${1}"
    exit 1
  fi

  shift

  local BUILDER="$(realpath "$(dirname "${BASH_SOURCE}")/builder")"
  if [[ ! -x "${BUILDER}" ]]; then
    echo "not executable: ${BUILDER}"
    exit 1
  fi

  set -o xtrace
  "${BUILDER}" "${BUILDER_ARGS[@]}" "${@}"
}

main "${@}"
