#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/../../../../../../scripts/common.sh"

set -o xtrace

cd "${HERE}/.."

pip3 install \
  --global-option=compile_schemas \
  --global-option="--import-path=${ROOT}/codex" \
  --editable '.[capnps]'
