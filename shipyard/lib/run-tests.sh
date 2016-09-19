#!/bin/bash

set -o xtrace

# HACK: Prevent unittest from loading shipyard/__init__.py (which will
# raise import errors due to path issues).
python3 -m unittest discover -s tests
