#!/bin/bash

# Set up environment for pylint

source "$(dirname "${BASH_SOURCE}")/common.sh"

exec pylint "${@}"
