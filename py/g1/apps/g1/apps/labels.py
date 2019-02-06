"""Helper for defining ``startup`` variable names."""

__all__ = [
    'Label',
    'make_labels',
]

import re

from g1.bases import collections
from g1.bases.assertions import ASSERT

PATTERN_PATH = re.compile(r'(?:[a-zA-Z_]\w*)(?:\.[a-zA-Z_]\w*)*')


def is_path(path):
    return PATTERN_PATH.fullmatch(path)


class Label(str):
    """Type-tagged string (for convenience)."""

    def __new__(cls, module_path, object_path):
        return super().__new__(
            cls,
            '%s:%s' % (
                ASSERT.predicate(module_path, is_path),
                ASSERT.predicate(object_path, is_path),
            ),
        )


def make_labels(module_path, *names, **names_labels):
    """Return a namespace of labels."""
    return collections.Namespace(
        *((name, Label(module_path, name)) for name in names),
        *((n, l if isinstance(l, Label) else Label(module_path, l))
          for n, l in names_labels.items()),
    )
