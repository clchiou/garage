#!/usr/bin/env bash
#
# Bundle together ``ctr`` and its dependencies in one zipapp.
#
# TODO: Eventually we should migrate this process to a build rule.
#

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ "${#}" -lt 1 ]]; then
  show "usage: ${PROG} [PYTHON3] OUTPUT"
  exit 1
fi

# Add buildtools to PYTHONPATH.
PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}${ROOT}/py/g1/devtools/buildtools"
# TODO: Remove this once we fully migrated to g1.devtools.buildtools.
PYTHONPATH="${PYTHONPATH}:${ROOT}/py/buildtools"
export PYTHONPATH

if [[ "${#}" -gt 1 ]]; then
  readonly PYTHON3="${1}"
  readonly USE_PYTHON3=(--python "${PYTHON3}")
  shift
else
  readonly PYTHON3=python3
  readonly USE_PYTHON3=()
fi

readonly OUTPUT="$(realpath "${1}")"
[[ -e "${OUTPUT}" ]] && abort "refuse to overwrite: ${OUTPUT}"

package() {
  show "goto: ${1}"
  cd "${ROOT}/py/${1}"
  rm -rf build  # Clean up previous build.
  trace_exec "${PYTHON3}" setup.py \
    build \
    bdist_zipapp "${USE_PYTHON3[@]}" --output "${OUTPUT}"
  rm -rf build
}

package "g1/apps"
package "g1/bases"
package "g1/containers"
package "g1/scripts"
package "startup"
