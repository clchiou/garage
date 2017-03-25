# Common part of all bash scripts

set -o errexit -o nounset -o pipefail

# Use the "outermost" source filename as the program name
readonly PROG="$(basename "${BASH_SOURCE[-1]}")"

show() {
  echo "${@}" 1>&2
}

info() {
  show "${PROG}: ${FUNCNAME[1]}: ${@}"
}

abort() {
  show "${PROG}: ${FUNCNAME[1]}: ${@}"
  exit 1
}

# ROOT is /path/to/garage
readonly ROOT="$(realpath "$(dirname "${BASH_SOURCE[0]}")/..")"
[[ -d "${ROOT}/.git" ]] || abort "not git repo: ${ROOT}"
