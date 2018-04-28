#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ "${#}" -lt 3 ]]; then
  show "usage: ${PROG} REPO[:TAG] BASE_BUILDER WAREHOUSE [BUILD_RULE]"
  exit 1
fi

cd "${ROOT}/shipyard"

confirm_exec \
  scripts/make-builder.sh \
    "${1}" \
    "${2}" \
    --volume "${3}:/home/plumber/input:ro" \
    --parameter '//base:release=true' \
    "${4:-//meta:third-party}"
