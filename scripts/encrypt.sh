#!/usr/bin/env bash

# Encrypt files and directories with gpgtar (gpg-zip is deprecated).

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ "${#}" -lt 2 ]]; then
  echo "usage: ${PROG} output input..."
  exit 1
fi

readonly OUTPUT="${1}"
shift

[[ ! -e "${OUTPUT}" ]] || abort "refuse to overwrite: ${OUTPUT}"

# Don't add `--encrypt`, which instructs gpg to use public key and is
# not what you intend to do.
set -o xtrace
gpgtar \
  --encrypt \
  --symmetric \
  --gpg-args '--openpgp --pinentry-mode loopback --cipher-algo AES256' \
  --output "${OUTPUT}" \
  "${@}"

gpg-connect-agent reloadagent /bye
