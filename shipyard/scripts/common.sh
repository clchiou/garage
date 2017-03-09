# Common part of scripts.

set -o errexit -o nounset -o pipefail

# ROOT is /path/to/garage.
readonly ROOT="$(realpath "$(dirname "${BASH_SOURCE}")/../..")"
if [[ ! -d "${ROOT}/.git" ]]; then
  echo "not git repo: ${ROOT}" 1>&2
  exit 1
fi

export PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${ROOT}/py/foreman:${ROOT}/py/garage:${ROOT}/py/startup:${ROOT}/shipyard"
echo "export PYTHONPATH=${PYTHONPATH}" 1>&2
