#!/bin/bash

set -o errexit -o nounset -o pipefail

source "$(dirname "${0}")/common.sh"

usage() {
  cat <<EOF
Usage: $(basename "${1}") [-h] [-y] [-n NAME] [-m MOUNT] [-f FLAGS] IMAGE [ARG...]

A thin wrapper of \`docker run\` where:

  * MOUNT are paths to data volumes.
  * FLAGS are options for docker.
  * ARG are arguments of the container.

After you are done with the builder, you may run:

  docker commit --change 'CMD ["/bin/bash"]' "\${NAME}" [TAG]

to tag it.
EOF
}

main() {
  local YES=0
  local NAME=""
  local MOUNT=()
  local FLAGS=""
  local opt=""
  while getopts ":hyn:m:f:" opt; do
    case "${opt}" in
      h) usage "${0}"; exit ;;
      y) YES=1 ;;
      n) NAME="${OPTARG}" ;;
      m) MOUNT+=("${OPTARG}") ;;
      f) FLAGS="${OPTARG}" ;;
      :) error "-${OPTARG} needs an argument" ;;
      *) error "Could not parse -${OPTARG}" ;;
    esac
  done
  shift $((OPTIND - 1))
  [[ -n "${NAME}" ]] && echo "NAME: ${NAME}"
  [[ "${#MOUNT[@]}" > 0 ]] && echo "MOUNT: ${MOUNT[@]}"
  [[ -n "${FLAGS}" ]] && echo "FLAGS: ${FLAGS}"

  local IMAGE="${1:-}"
  if [[ -z "${IMAGE}" ]]; then
    usage "${0}"
    exit 1
  fi
  shift
  echo "IMAGE: ${IMAGE}"
  [[ "${#}" > 0 ]] && echo "ARG: ${@}"

  local REPO_ROOT="$(repo_root)"
  echo "REPO_ROOT: ${REPO_ROOT}"

  local VOLUME=()
  local mount_point=""
  for mount_point in "${MOUNT[@]:+${MOUNT[@]}}"; do
    mount_point="$(realpath "${mount_point}")"
    VOLUME+=("--volume")
    VOLUME+=("${mount_point}:/home/plumber/$(basename "${mount_point}"):ro")
  done

  [[ "${YES}" = 0 ]] && ask

  set -o xtrace
  docker run \
    ${FLAGS} \
    ${NAME:+--name} ${NAME} \
    --volume "${REPO_ROOT}:/home/plumber/garage:ro" \
    "${VOLUME[@]:+${VOLUME[@]}}" \
    "${IMAGE}" "${@}"
}

main "${@}"
