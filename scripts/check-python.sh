#!/usr/bin/env bash

# Run checks on a Python project.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

main() {
  echo '=== unittest ==='
  python3 -m unittest

  local -r srcs=($(list_python_srcs))

  echo
  echo '=== yapf ==='
  yapf --verbose --diff "${srcs[@]}"

  echo
  echo '=== pylint ==='
  pylint "${srcs[@]}"
}

list_python_srcs() {
  cat <(_list_python_srcs_1) <(_list_python_srcs_2) \
    | cut -d/ -f2- \
    | sort \
    | uniq
}

_list_python_srcs_1() {
  find . \
    -not -path './build*' \
    -not -path './frontend*' \
    -not -name '*.py' \
    -exec bash -c 'file {} | grep -q "Python script" && echo {}' \;
}

_list_python_srcs_2() {
  find . \
    -not -path './build*' \
    -not -path './frontend*' \
    -name '*.py'
}

main "${@}"
