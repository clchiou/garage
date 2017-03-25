source "$(dirname "${BASH_SOURCE[0]}")/../../scripts/common.sh"

# Put shipyard at first so that `import tests` would import ours
export PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${ROOT}/shipyard:${ROOT}/py/foreman:${ROOT}/py/garage:${ROOT}/py/startup"
