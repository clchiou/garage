#!/bin/bash

set -o errexit -o nounset -o pipefail

source "$(dirname "${0}")/common.sh"

usage() {
  cat <<EOF
Usage: $(basename ${1}) TAG

Make and tag a base builder Docker image.  You may later run this base
builder image to build your final output.
EOF
}

main() {
  if [[ -z "${1:-}" ]]; then
    usage "${0}"
    exit 1
  fi

  local TAG="${1}"

  local BOOTSTRAP="$(fullpath_from_scripts ../bootstrap)"
  echo "BOOTSTRAP=${BOOTSTRAP}"

  ask

  set -o xtrace
  docker build --tag "${TAG}" "${BOOTSTRAP}"
}

main "${@}"
