#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [[ "${#}" -lt 2 ]]; then
  show "usage: ${PROG} BUILDER_VERSION OUTPUT"
  exit 1
fi

trace_exec sudo -v

# This version has to match the version defined in ``ctr``.
readonly BASE_VERSION=0.0.1

readonly BUILDER_VERSION="${1}"

readonly OUTPUT="$(realpath "${2}")"
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

generate_files() {
  show "generate: ${TMPDIR}/builder-base.json"
  cat >"${TMPDIR}/builder-base.json" <<END
{
  "name": "builder",
  "version": "${BUILDER_VERSION}",
  "apps": [
    {
      "name": "builder",
      "type": "oneshot",
      "exec": ["/root/build.sh"],
      "user": "root",
      "group": "root"
    }
  ],
  "images": [
    {"name": "base", "version": "${BASE_VERSION}"},
    {"name": "base-extra", "version": "${BASE_VERSION}"}
  ],
  "volumes": [
    {"source": "${TMPDIR}/build.sh", "target": "/root/build.sh"}
  ]
}
END

  show "generate: ${TMPDIR}/build.sh"
  cat >"${TMPDIR}/build.sh" <<END
#!/usr/bin/env bash

set -o errexit -o nounset -o pipefail -o xtrace

adduser --disabled-password --gecos "" plumber
echo "plumber ALL=(ALL:ALL) NOPASSWD: ALL" > /etc/sudoers.d/99-plumber
chmod 440 /etc/sudoers.d/99-plumber
END
  chmod +x "${TMPDIR}/build.sh"
}

find_image() {
  ctr images list --format csv --header false --columns name,version \
    | tr --delete '\r' \
    | grep --silent --fixed-strings --line-regexp "${1},${2}"
}

if ! find_image base-extra "${BASE_VERSION}"; then
  if find_image base "${BASE_VERSION}"; then
    abort "expect base image does not exist"
  fi
  trace_exec sudo "${CTR}" images build-base \
    --prune-stash-path "${TMPDIR}/base-extra" \
    "${TMPDIR}/base.tgz"
  sudo chown "${OWNER}:${GROUP}" "${TMPDIR}/base.tgz"
  trace_exec sudo "${CTR}" images import "${TMPDIR}/base.tgz"
  trace_exec mv "${TMPDIR}/base.tgz" "${OUTPUT}"

  trace_exec sudo "${CTR}" images build \
    --nv base-extra "${BASE_VERSION}" \
    --rootfs "${TMPDIR}/base-extra" \
    "${TMPDIR}/base-extra.tgz"
  sudo chown "${OWNER}:${GROUP}" "${TMPDIR}/base-extra.tgz"
  trace_exec sudo "${CTR}" images import "${TMPDIR}/base-extra.tgz"
  trace_exec mv "${TMPDIR}/base-extra.tgz" "${OUTPUT}"
else
  show "skip generating base and base-extra"
fi

if ! find_image builder-base "${BUILDER_VERSION}"; then
  readonly POD_ID="$("${CTR}" pods generate-id)"
  show "use pod id: ${POD_ID}"
  generate_files
  trace_exec sudo "${CTR}" pods run \
    --id "${POD_ID}" \
    "${TMPDIR}/builder-base.json"
  trace_exec sudo "${CTR}" pods export-overlay \
    --include '/etc/' \
    --include '/etc/**' \
    --include '/home/' \
    --include '/home/**' \
    --exclude '*' \
    "${POD_ID}" \
    "${TMPDIR}/builder-base"
  trace_exec sudo "${CTR}" images build \
    --nv builder-base "${BUILDER_VERSION}" \
    --rootfs "${TMPDIR}/builder-base" \
    "${TMPDIR}/builder-base.tgz"
  sudo chown "${OWNER}:${GROUP}" "${TMPDIR}/builder-base.tgz"
  trace_exec sudo "${CTR}" images import "${TMPDIR}/builder-base.tgz"
  trace_exec mv "${TMPDIR}/builder-base.tgz" "${OUTPUT}"
  trace_exec sudo "${CTR}" pods remove "${POD_ID}"
else
  show "skip generating builder-base"
fi
