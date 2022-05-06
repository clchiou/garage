#!/usr/bin/env bash

# Build the extension and the test-helper extension in-place.

source "$(dirname "${BASH_SOURCE[0]}")/../../../../../scripts/common.sh"

trace_exec python3 setup.py build_ext --inplace
trace_exec python3 setup_tests.py build_ext --inplace
