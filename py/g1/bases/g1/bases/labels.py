"""Labels.

Labels are a convenient way to refer to global variables.
"""

__all__ = [
    'Label',
    'make_labels',
    'make_nested_labels',
    'load_global',
]

import re

from . import collections
from .assertions import ASSERT

# XXX: Import this module lazily.  Or does it really matter?
importlib = None

# Module path only accepts identifiers.
PATTERN_MODULE_PATH = re.compile(
    r'''
    (?:[a-zA-Z_]\w*)
    (?:\.[a-zA-Z_]\w*)*
    ''',
    re.VERBOSE,
)

# Object path accepts both identifiers and numeric element indexes (this
# is a strict subset of ``str.format``).
# XXX: Should we also accept string literals as indexes?
PATTERN_OBJECT_PATH = re.compile(
    r'''
    (?:[a-zA-Z_]\w*)
    (?: \.[a-zA-Z_]\w* | \[\d+\])*
    ''',
    re.VERBOSE,
)
PATTERN_FIELD_NAME = re.compile(
    r'\.?([a-zA-Z_]\w*) | \[(\d+)\]',
    re.VERBOSE,
)


class Label(str):

    __slots__ = (
        'module_path',
        'object_path',
    )

    @classmethod
    def parse(cls, label_str):
        i = label_str.index(':')
        return cls(label_str[:i], label_str[i + 1:])

    def __new__(cls, module_path, object_path):
        return super().__new__(
            cls,
            '%s:%s' % (
                ASSERT.predicate(module_path, PATTERN_MODULE_PATH.fullmatch),
                ASSERT.predicate(object_path, PATTERN_OBJECT_PATH.fullmatch),
            ),
        )

    def __init__(self, module_path, object_path):
        # pylint: disable=super-init-not-called
        # ``str`` does not define ``__init__`` (nor should we call it?).

        # ``__new__`` has checked these paths.
        self.module_path = module_path
        self.object_path = object_path


def make_labels(module_path, *names, **names_labels):
    """Make a namespace of labels."""
    return collections.Namespace(
        *((name, Label(module_path, name)) for name in names),
        *((n, l if isinstance(l, Label) else Label(module_path, l))
          for n, l in names_labels.items()),
    )


def make_nested_labels(module_path, root):
    """Make nested namespaces of labels.

    The input format is quite flexible (maybe too flexible).  Basically,
    you specify namespace paths in a tree structure, and this generates
    nested namespaces in which the leaves are labels.  The object path
    of a label is the same as its namespace path.

    ``root`` is the root node, and each node is an iterable, of which
    elements may be a string or a pair.

    * If an element is a string, it is a namespace path to a leaf.

    * If it is a pair, it is a namespace path and a node.
    """

    object_path = []

    def make(node):
        entries = []
        for str_or_pair in node:
            if isinstance(str_or_pair, str):
                object_path.append(str_or_pair)
                entries.append(
                    (str_or_pair, Label(module_path, '.'.join(object_path)))
                )
                object_path.pop()
            else:
                path, another_node = str_or_pair
                object_path.append(path)
                entries.append((path, make(another_node)))
                object_path.pop()
        return collections.Namespace(*entries)

    return make(root)


def load_global(label, *, invalidate_caches=False):
    """Load global variable pointed by ``label``."""

    global importlib
    if importlib is None:
        # pylint: disable=redefined-outer-name
        import importlib

    if not isinstance(label, Label):
        label = Label.parse(label)

    if invalidate_caches:
        importlib.invalidate_caches()

    value = importlib.import_module(label.module_path)
    for match in PATTERN_FIELD_NAME.finditer(label.object_path):
        if match.group(1):
            value = getattr(value, match.group(1))
        else:
            value = value[int(ASSERT.true(match.group(2)))]

    return value
