#!/usr/bin/env bash

# Fetch envoy binary from official release image.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ "${#}" -lt 1 ]]; then
  abort "usage: $(basename "${0}") version [output]"
fi

readonly VERSION="${1}"
readonly OUTPUT_PATH="${2:-"$(pwd)/envoy"}"

[[ ! -e "${OUTPUT_PATH}" ]] || abort "refuse to overwrite: ${OUTPUT_PATH}"

readonly OUTPUT_DIR="$(realpath "$(dirname "${OUTPUT_PATH}")")"
readonly OUTPUT_NAME="$(basename "${OUTPUT_PATH}")"

ensure_directory "${OUTPUT_DIR}"

info "fetch envoy:${VERSION} -> ${OUTPUT_PATH}"

set -o xtrace

docker pull "lyft/envoy:${VERSION}"

docker run \
  --rm \
  --volume "${OUTPUT_DIR}:/output" \
  "lyft/envoy:${VERSION}" \
  cp /usr/local/bin/envoy "/output/${OUTPUT_NAME}"
