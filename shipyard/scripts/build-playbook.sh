#!/bin/bash

set -o errexit -o nounset -o pipefail

main() {
  if [[ "${#}" < 3 ]]; then
    echo "Usage: $(basename ${0}) IMAGE PLAYBOOK TAG"
    exit 1
  fi

  local IMAGE="${1}"
  local PLAYBOOK="${2}"
  local TAG="${3}"

  local GARAGE_PATH="$(fullpath "$(dirname ${0})/../..")"
  echo "GARAGE_PATH: ${GARAGE_PATH}"

  local CONTAINER_NAME="${PLAYBOOK%.*}-$(date +%Y%m%d-%H%M)"
  echo "CONTAINER_NAME: ${CONTAINER_NAME}"

  set -o xtrace

  docker run \
    --name "${CONTAINER_NAME}" \
    --volume "${GARAGE_PATH}:/home/plumber/garage:ro" \
    "${IMAGE}" \
    /bin/bash -c "cd garage/shipyard && ansible-playbook ${PLAYBOOK}"

  docker commit --change 'CMD ["/bin/bash"]' "${CONTAINER_NAME}" "${TAG}"

  docker rm "${CONTAINER_NAME}"
}

fullpath() {
  cd "${1}"; pwd; cd - > /dev/null
}

main $@
