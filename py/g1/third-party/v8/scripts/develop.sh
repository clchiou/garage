#!/usr/bin/env bash

# Build package in place.

source "$(dirname "${BASH_SOURCE[0]}")/../../../../../scripts/common.sh"

[[ "${#}" -ge 1 ]] || abort "usage: ${0} /path/to/v8 [{x64.release|...} [/path/to/boost]]"

readonly PROJECT="$(realpath "${HERE}/..")"

readonly V8="$(realpath "${1}")"
ensure_directory "${V8}"

readonly CONFIG="${2:-x64.release}"
ensure_directory "${V8}/out.gn/${CONFIG}"

readonly BOOST="${3:-}"

INCLUDE_DIRS="${V8}:${V8}/include"
LIBRARY_DIRS="${V8}/out.gn/${CONFIG}/obj"
if [[ -n "${BOOST}" ]]; then
  INCLUDE_DIRS+=":${BOOST}/include"
  LIBRARY_DIRS+=":${BOOST}/lib"
fi

set -o xtrace
cd "${PROJECT}"
pip3 install \
  --global-option=copy_files \
  --global-option="--src-dir=${V8}/out.gn/${CONFIG}" \
  --global-option=build_ext \
  --global-option=--inplace \
  --global-option="--include-dirs=${INCLUDE_DIRS}" \
  --global-option="--library-dirs=${LIBRARY_DIRS}" \
  --editable .
