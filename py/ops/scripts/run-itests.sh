#!/bin/bash

# Run integration tests.

set -o errexit -o nounset -o pipefail

main() {
  if [[ -z "${1:-}" ]]; then
    echo "Usage: $(basename "${0}") test_runner_image"
    exit 1
  fi

  local NAME="tester-$(date +%s)"

  local HERE="$(realpath "$(dirname "${BASH_SOURCE}")/..")"

  set -o xtrace

  # Make sure test_pkgs is the first so that all runtime dependencies
  # are installed before the rest of the tests are executed.
  docker run \
    --name "${NAME}" \
    --volume "${HERE}:/home/plumber/ops" \
    --workdir "/home/plumber/ops" \
    "${1}" \
    python3 -m unittest --verbose --failfast \
    itests.test_pkgs \
    itests.test_apps

  # Removes the container only when success so that you may examine the
  # contents when fail.
  docker rm "${NAME}"
}

main "${@}"
