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


def make_nested_labels(module_path, root):
    """Make a nested namespace."""

    object_path = []

    def make(node):
        entries = []
        for pair in get_items(node):
            if isinstance(pair, str):
                name = value = pair
            else:
                name, value = pair
            if isinstance(value, str):
                object_path.append(value)
                entries.append(
                    (name, Label(module_path, '.'.join(object_path)))
                )
                object_path.pop()
            else:
                object_path.append(name)
                entries.append((name, make(value)))
                object_path.pop()
        return collections.Namespace(*entries)

    def get_items(node):
        if hasattr(node, 'items'):
            return node.items()
        else:
            # Assume it's a list of pairs.
            return node

    return make(root)
