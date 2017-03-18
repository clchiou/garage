# Common part of scripts.

set -o errexit -o nounset -o pipefail

# ROOT is /path/to/garage.
readonly ROOT="$(realpath "$(dirname "${BASH_SOURCE}")/../..")"
if [[ ! -d "${ROOT}/.git" ]]; then
  echo "not git repo: ${ROOT}" 1>&2
  exit 1
fi

# Put shipyard at first so that `import tests` would import ours
export PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${ROOT}/shipyard:${ROOT}/py/foreman:${ROOT}/py/garage:${ROOT}/py/startup"
echo "export PYTHONPATH=${PYTHONPATH}" 1>&2
