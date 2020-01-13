#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# Because sudo does not search into custom paths, let's look it up
# before sudo.
exec sudo "$(which ctr)" "${@}"
