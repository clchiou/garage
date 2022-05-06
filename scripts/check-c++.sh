#!/usr/bin/env bash

# Run checks on C++ source files.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

readonly SRCS=($(find . -name '*.h' -or -name '*.cc' | sort | cut -d/ -f2-))

for src in "${SRCS[@]}"; do
  echo "=== clang-format ${src} ==="
  clang-format "${src}" | diff "${src}" -
done
