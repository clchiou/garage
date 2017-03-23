#!/bin/bash

# Set up environment for python3

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

exec python3 "${@}"
