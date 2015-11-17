#!/bin/bash

set -o errexit -o nounset -o pipefail

source "$(dirname "${0}")/common.sh"

usage() {
  cat <<EOF
Usage: $(basename ${1}) [-h] [-n NAME] [-f FLAGS] IMAGE [ARG...]

Pass FLAGS to \`docker run\` to start a container from IMAGE with NAME,
and then pass ARG to the container.
EOF
}

main() {
  local NAME=""
  local FLAGS=""
  local opt=""
  while getopts ":hn:f:" opt; do
    case "${opt}" in
      h) usage "${0}"; exit ;;
      n) NAME="${OPTARG}" ;;
      f) FLAGS="${OPTARG}" ;;
      :) error "-${OPTARG} needs an argument" ;;
      *) error "Could not parse -${OPTARG}" ;;
    esac
  done
  shift $((OPTIND - 1))
  [[ -n "${NAME}" ]] && echo "NAME: ${NAME}"
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

  ask

  set -o xtrace
  docker run \
    ${FLAGS} \
    ${NAME:+--name} ${NAME} \
    --volume "${REPO_ROOT}:/home/plumber/garage:ro" \
    "${IMAGE}" "${@}"
}

main "${@}"
