#!/bin/bash

# Handy wrapper for building all packages.

set -o errexit -o nounset -o pipefail

main() {
  local BUILDER="$(realpath "$(dirname "${BASH_SOURCE}")/builder")"
  if [[ ! -x "${BUILDER}" ]]; then
    echo "not executable: ${BUILDER}"
    exit 1
  fi

  # Enumerate all packages here.
  set -o xtrace
  "${BUILDER}" build \
    //cpython:build \
    //garage:build \
    //http2:build \
    //lxml:build \
    //mako:build \
    //nanomsg:build \
    //nanomsg/py:build \
    //nghttp2:build \
    //pyyaml:build \
    //requests:build \
    //sqlalchemy:build \
    //startup:build \
    //v8:build \
    //v8/py:build \
    "${@}"
}

main "${@}"
