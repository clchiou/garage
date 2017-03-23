#!/bin/bash

# Make builder image
#   * You usually use (cached) builder images to reduce dev build time
#   * By default this script builds //meta:third-party

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ "${#}" -lt 2 ]]; then
  show "usage: ${PROG} REPO[:TAG] BASE_BUILDER [BUILD_ARGS...]"
  exit 1
fi

readonly BUILD_NAME="build-$(date +%s)"
readonly REPO_TAG="${1}"
readonly BASE_BUILDER="${2}"
shift 2

set -o xtrace

cd "${ROOT}/shipyard"

scripts/builder build \
  --build-name "${BUILD_NAME}" \
  --builder "${BASE_BUILDER}" \
  --preserve-container \
  "${@:-//meta:third-party}"

docker commit --change 'CMD ["/bin/bash"]' "${BUILD_NAME}" "${REPO_TAG}"

docker rm "${BUILD_NAME}"
