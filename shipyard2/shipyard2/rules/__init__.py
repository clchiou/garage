"""Helpers for writing build rules."""

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())


def canonicalize_name_prefix(name_prefix):
    if name_prefix:
        if not name_prefix.endswith('/'):
            name_prefix += '/'
        return name_prefix
    else:
        return ''
