# Common part of all bash scripts

set -o errexit -o nounset -o pipefail

# Use the "outermost" source filename as the program name
readonly PROG="$(basename "${BASH_SOURCE[-1]}")"

show() {
  echo "${@}" 1>&2
}

abort() {
  show "${PROG}: ${FUNCNAME[1]}: ${@}"
  exit 1
}

# ROOT is /path/to/garage
readonly ROOT="$(realpath "$(dirname "${BASH_SOURCE[0]}")/..")"
[[ -d "${ROOT}/.git" ]] || abort "not git repo: ${ROOT}"

# Helper functions

info() {
  show "${PROG}: ${FUNCNAME[1]}: ${@}"
}

# Use this if you don't want to enable xtrace
log_and_run() {
  show "+ ${@}"
  "${@}"
}

ensure_file() {
  [[ -f "${1}" ]] || abort "not a file: ${1}"
}

ensure_directory() {
  [[ -d "${1}" ]] || abort "not a directory: ${1}"
}