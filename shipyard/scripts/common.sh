# Common part of scripts

set -o errexit -o nounset -o pipefail

# Use the "outermost" source filename as the program name
readonly PROG="$(basename "${BASH_SOURCE[-1]}")"

show() {
  echo "${@}" 1>&2
}

# ROOT is /path/to/garage
readonly ROOT="$(realpath "$(dirname "${BASH_SOURCE[0]}")/../..")"
if [[ ! -d "${ROOT}/.git" ]]; then
  show "${PROG}: not git repo: ${ROOT}"
  exit 1
fi

# Put shipyard at first so that `import tests` would import ours
export PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${ROOT}/shipyard:${ROOT}/py/foreman:${ROOT}/py/garage:${ROOT}/py/startup"
show "export PYTHONPATH=${PYTHONPATH}"
