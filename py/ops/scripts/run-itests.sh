#!/bin/bash

# Run integration tests

source "$(dirname "${BASH_SOURCE[0]}")/../../../scripts/common.sh"

if [[ "${#}" -lt 1 ]]; then
  show "usage: ${PROG} TEST_RUNNER [TARBALL_DIR]"
  exit 1
fi

readonly NAME="test-$(date +%s)"

if [[ -n "${2:-}" ]]; then
  readonly TARBALL_VOLUME="--volume ${2}:/tmp/tarballs:ro"
fi

set -o xtrace

# Make sure test_deps is the first so that all runtime dependencies are
# installed before the rest of the tests are executed
docker run \
  --name "${NAME}" \
  --env PYTHONPATH="/home/plumber/garage/py/garage:/home/plumber/garage/py/startup" \
  --volume "${ROOT}:/home/plumber/garage:ro" \
  ${TARBALL_VOLUME:-} \
  --workdir "/home/plumber/garage/py/ops" \
  "${1}" \
  python3 -m unittest --verbose --failfast \
  itests.test_deps \
  itests.test_pods \
  itests.test_pods_http \
  itests.test_pods_ports \

# Removes the container only when success so that you may examine the
# contents when fail
docker rm "${NAME}"
