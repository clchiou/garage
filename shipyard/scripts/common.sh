# Helper functions.

error() {
  echo ERROR: $@ 1>&2
  exit 1
}

realpath_from_scripts() {
  realpath "$(dirname "${BASH_SOURCE}")/${1}"
}

repo_root() {
  local ROOT="$(realpath_from_scripts ../..)"
  if [[ ! -d "${ROOT}/.git" && "${ROOT##*/}" != "garage" ]]; then
    error "'${ROOT}' does not look like the repo"
  fi
  echo "${ROOT}"
}

ask() {
  if ! tty --silent; then
    return  # stdin is not a tty.
  fi

  local yes
  read -p "${1:-Proceed?} [yN] " yes
  if [[ "${yes}" != "Y" && "${yes}" != "y" ]]; then
    exit
  fi
}
