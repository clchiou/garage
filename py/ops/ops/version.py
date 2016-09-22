__all__ = [
    'VERSION',
    'get_data_dir',
]

from pathlib import Path


# This is the version of the on-disk data format.
VERSION = 1


def get_data_dir(ops_data):
    return Path(ops_data).absolute() / ('v%d' % VERSION)
