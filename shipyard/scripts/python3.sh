#!/bin/bash

# Set up environment for python3

source "$(dirname "${BASH_SOURCE}")/common.sh"

exec python3 "${@}"
