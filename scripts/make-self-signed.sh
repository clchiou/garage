#!/usr/bin/env bash

# Make a development self-signed certificate.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ "${#}" -ne 4 ]]; then
  echo "usage: ${PROG} output_key output_crt output_dh output_pem"
  exit 1
fi

readonly OUTPUT_KEY="${1}"
readonly OUTPUT_CRT="${2}"
readonly OUTPUT_DH="${3}"
readonly OUTPUT_PEM="${4}"

[[ ! -e "${OUTPUT_KEY}" ]] || abort "refuse to overwrite: ${OUTPUT_KEY}"
[[ ! -e "${OUTPUT_CRT}" ]] || abort "refuse to overwrite: ${OUTPUT_CRT}"
[[ ! -e "${OUTPUT_DH}" ]] || abort "refuse to overwrite: ${OUTPUT_DH}"
[[ ! -e "${OUTPUT_PEM}" ]] || abort "refuse to overwrite: ${OUTPUT_PEM}"

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

# Strangely, if you put `-out` before 4096, openssl will output to
# stdout rather than the output file you specify.
trace_exec \
  openssl dhparam -out "${OUTPUT_DH}" 4096

cat "${OUTPUT_CRT}" "${OUTPUT_KEY}" "${OUTPUT_DH}" > "${OUTPUT_PEM}"
