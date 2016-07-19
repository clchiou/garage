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
      //cc/nanomsg:build
      //cc/nghttp2:build
      //cc/v8:build
      //py/cpython:build
      //py/garage:build
      //py/http2:build
      //py/lxml:build
      //py/mako:build
      //py/nanomsg:build
      //py/pyyaml:build
      //py/requests:build
      //py/sqlalchemy:build
      //py/startup:build
      //py/v8:build
    )
    # And all host tools, too.
    BUILDER_ARGS+=(
      //host/cpython:install
      //host/mako:install
      //host/node:install
    )
  elif [[ "${1}" = "echod" ]]; then
    BUILDER_ARGS+=(
      //py/garage/examples/echod:build_pod
      --parameter "//py/garage/examples/echod:version=${VERSION}"
    )
  elif [[ "${1}" = "httpd" ]]; then
    BUILDER_ARGS+=(
      //py/cpython/examples/httpd:build_pod
      --parameter "//py/cpython/examples/httpd:version=${VERSION}"
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
