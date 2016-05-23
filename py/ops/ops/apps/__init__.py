"""Manage containerized application images."""

import argparse
import logging
from pathlib import Path

from ops import commands


LOG = logging.getLogger(__name__)


def main(argv):
    parser = argparse.ArgumentParser(prog=__name__, description=__doc__)
    return 0
