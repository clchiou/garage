#!/usr/bin/env bash

# Build py/v8 in place.

source "$(dirname "${BASH_SOURCE[0]}")/../../../scripts/common.sh"

[[ "${#}" -eq 3 ]] || abort "usage: /path/to/v8 {x64.debug|...} /path/to/installed/lib"

readonly PROJECT="$(realpath "$(dirname "${BASH_SOURCE[0]}")/..")"

readonly V8_PATH="$(realpath "${1}")"
ensure_directory "${V8_PATH}"

readonly CONFIG="${2}"
ensure_directory "${V8_PATH}/out.gn/${CONFIG}"

readonly LIB_PATH="$(realpath "${3}")"
ensure_directory "${LIB_PATH}"

set -o xtrace
cd "${PROJECT}"
pip3 install \
  --global-option=copy_files \
  --global-option="--src-dir=${V8_PATH}/out.gn/${CONFIG}" \
  --global-option=build_ext \
  --global-option=--inplace \
  --global-option="--include-dirs=${V8_PATH}:${V8_PATH}/include" \
  --global-option="--library-dirs=${LIB_PATH}" \
  --editable .
