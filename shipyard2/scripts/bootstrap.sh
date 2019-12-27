#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ "${#}" -ne 1 ]]; then
  show "usage: ${PROG} OUTPUT"
  exit 1
fi

trace_exec sudo -v

# This version has to match the version defined in ``ctr``.
readonly BASE_VERSION=0.0.1

readonly OUTPUT="$(realpath "${1}")"
ensure_directory "${OUTPUT}"

# Resolve ``ctr``'s real location because ``sudo`` does not look up
# custom paths.
readonly CTR="$(which ctr)"
show "use ctr: ${CTR}"

readonly OWNER="$(id --user --name)"
readonly GROUP="$(id --group --name)"

readonly TMPDIR="$(mktemp --directory --tmpdir="${OUTPUT}")"
ensure_directory "${TMPDIR}"
trap "sudo rm --force --recursive '${TMPDIR}'" EXIT
show "use temporary directory: ${TMPDIR}"

find_image() {
  ctr images list --format csv --header false --columns name,version \
    | tr --delete '\r' \
    | grep --silent --fixed-strings --line-regexp "${1},${2}"
}

move_image() {
  sudo chown "${OWNER}:${GROUP}" "${TMPDIR}/${1}"
  trace_exec sudo "${CTR}" images import "${TMPDIR}/${1}"
  trace_exec mv "${TMPDIR}/${1}" "${OUTPUT}"
}

if find_image base-extra "${BASE_VERSION}"; then
  show "skip generating base and base-extra"
  exit
fi

if find_image base "${BASE_VERSION}"; then
  abort "expect base image does not exist"
fi

trace_exec sudo "${CTR}" images build-base \
  --prune-stash-path "${TMPDIR}/base-extra" \
  "${TMPDIR}/base.tgz"
trace_exec sudo "${CTR}" images build \
  --nv base-extra "${BASE_VERSION}" \
  --rootfs "${TMPDIR}/base-extra" \
  "${TMPDIR}/base-extra.tgz"
move_image base.tgz
move_image base-extra.tgz
