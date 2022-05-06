#!/usr/bin/env bash

# Run Python coverage.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

coverage run -m unittest
coverage report --ignore-errors
coverage erase
