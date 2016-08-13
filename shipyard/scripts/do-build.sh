#!/bin/bash

# Handy shortcuts for launching builder.

set -o errexit -o nounset -o pipefail

main() {
  if [[ -z "${1:-}" ]]; then
    echo "Usage: $(basename "${0}") {all|third-party|echod|httpd|nghttpx} --builder BUILDER --preserve-container --output OUTPUT ..."
    exit 1
  fi

  local VERSION="${VERSION:-$(date +%s)}"

  local THIRD_PARTY=(
    //cc/nanomsg:build
    //cc/nghttp2:build
    //cc/v8:build
    //host/cpython:install
    //host/docker2aci:install
    //host/java:install
    //host/mako:install
    //host/node:install
    //java/java:build
    //py/cpython:build
    //py/cpython:install_cython
    //py/lxml:build
    //py/mako:build
    //py/pyyaml:build
    //py/requests:build
    //py/sqlalchemy:build
  )

  local BUILDER_ARGS=(build)
  if [[ "${1}" = "all" ]]; then
    BUILDER_ARGS+=(
      //java/garage:build
      //py/garage:build
      //py/http2:build
      //py/nanomsg:build
      //py/startup:build
      //py/v8:build
    )
    BUILDER_ARGS+=("${THIRD_PARTY[@]}")
  elif [[ "${1}" = "third-party" ]]; then
    # Build all third-party packages (including all host tools).
    BUILDER_ARGS+=("${THIRD_PARTY[@]}")
  elif [[ "${1}" = "echod" ]]; then
    BUILDER_ARGS+=(
      //py/garage/examples/echod:build_pod/echod
      --parameter "//py/garage/examples/echod:version=${VERSION}"
    )
  elif [[ "${1}" = "httpd" ]]; then
    BUILDER_ARGS+=(
      //py/cpython/examples/httpd:build_pod/httpd
      --parameter "//py/cpython/examples/httpd:version=${VERSION}"
    )
  elif [[ "${1}" = "nghttpx" ]]; then
    BUILDER_ARGS+=(
      //cc/nghttp2/nghttpx:build_image/nghttpx
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
