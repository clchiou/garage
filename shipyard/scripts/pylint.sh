#!/usr/bin/env bash

# Set up environment for pylint

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

exec pylint "${@}"
