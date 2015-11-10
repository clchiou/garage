#!/bin/bash

# Usage: build-cpython.sh [DOCKER_HUB_REPO [CPYTHON_REV]]

set -o errexit -o nounset -o pipefail

CPYTHON_REV="${2:-v3.5.0}"
echo "CPYTHON_REV: ${CPYTHON_REV}"

TAG="${1:-cpython}:${CPYTHON_REV}"
echo "TAG: ${TAG}"

set -o xtrace

docker build \
  --tag "${TAG}" \
  --build-arg "CPYTHON_REV=${CPYTHON_REV}" \
  cpython
