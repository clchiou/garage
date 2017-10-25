#!/usr/bin/env bash

# Make a development self-signed certificate.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ "${#}" -ne 2 ]]; then
  echo "usage: ${PROG} output_key output_crt"
  exit 1
fi

readonly OUTPUT_KEY="${1}"
readonly OUTPUT_CRT="${2}"

[[ ! -e "${OUTPUT_KEY}" ]] || abort "refuse to overwrite: ${OUTPUT_KEY}"
[[ ! -e "${OUTPUT_CRT}" ]] || abort "refuse to overwrite: ${OUTPUT_CRT}"

export TZ=UTC

trace_exec \
  faketime -f "$(date +%Y)-01-01 00:00:00" \
  openssl req \
    -x509 \
    -newkey rsa:4096 \
    -sha256 \
    -nodes \
    -subj '/C=US/ST=CA/O=dev/CN=localhost' \
    -days 730 \
    -keyout "${OUTPUT_KEY}" \
    -out "${OUTPUT_CRT}"

trace_exec \
  openssl x509 -in "${OUTPUT_CRT}" -noout -text
