#!/bin/bash

if [[ -z "${1}" ]]; then
  echo "Usage: $(basename ${0}) DST_DIR"
  echo "  Copy cpython build artifacts to DST_DIR"
  exit 1
fi

set -o errexit -o xtrace

# Copy build artifacts and dependent shared libraries, excluding tests
# and some modules.

rsync --verbose \
  --archive \
  --relative \
  --exclude '/usr/local/lib/python*/idlelib' \
  --exclude '/usr/local/lib/python*/lib2to3' \
  --exclude '/usr/local/lib/python*/tkinter' \
  --exclude '/usr/local/lib/python*/turtledemo' \
  --exclude '/usr/local/lib/python*/ctypes/test' \
  --exclude '/usr/local/lib/python*/distutils/tests' \
  --exclude '/usr/local/lib/python*/sqlite3/test' \
  --exclude '/usr/local/lib/python*/test' \
  --exclude '/usr/local/lib/python*/unittest/test' \
  '/lib/x86_64-linux-gnu' \
  '/lib64' \
  '/usr/local/bin' \
  '/usr/local/lib' \
  /usr/lib/x86_64-linux-gnu/libgdbm.so.* \
  /usr/lib/x86_64-linux-gnu/libgdbm_compat.so.* \
  /usr/lib/x86_64-linux-gnu/libpanelw.so.* \
  /usr/lib/x86_64-linux-gnu/libsqlite3.so.* \
  "${1}"
