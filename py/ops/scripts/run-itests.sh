#!/bin/bash

# Run integration tests.

set -o errexit -o nounset -o pipefail

main() {
  if [[ -z "${1:-}" ]]; then
    echo "Usage: $(basename "${0}") test_runner_image"
    exit 1
  fi

  local HERE="$(realpath "$(dirname "${BASH_SOURCE}")/..")"

  set -o xtrace

  # Make sure test_pkgs is the first so that all runtime dependencies
  # are installed before the rest of the tests are executed.
  docker run \
    --rm \
    --volume "${HERE}:/home/plumber/ops" \
    --workdir "/home/plumber/ops" \
    "${1}" \
    python3 -m unittest --verbose \
    itests.test_pkgs \
    itests.test_apps
}

main "${@}"
