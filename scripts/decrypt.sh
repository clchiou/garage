#!/usr/bin/env bash

# Decrypt an archive with gpgtar (gpg-zip is deprecated).

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ "${#}" -ne 1 ]]; then
  echo "usage: ${PROG} archive"
  exit 1
fi

ensure_file "${1}"

set -o xtrace
gpgtar \
  --decrypt \
  --gpg-args '--openpgp --pinentry-mode loopback' \
  --directory . \
  "${1}"

gpg-connect-agent reloadagent /bye
