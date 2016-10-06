__all__ = [
    'NodeTable',
]

from collections import OrderedDict
from functools import partialmethod

from .schema import Node


def is_struct_or_enum(node):
    return node.is_struct() or node.is_enum()


class NodeTable:

    def __init__(self, nodes):
        self._nodes = OrderedDict((node.id, node) for node in nodes)

        # Attach info to nodes.

        self._filenames = {}

        self._cc_classnames = {}
        self._cython_classnames = {}
        self._python_classnames = {}

        self._cc_reader_member_functions_table = {}
        self._cc_builder_member_functions_table = {}

        self._enum_members_table = {}

    def __iter__(self):
        return iter(self._nodes)

    def items(self):
        return self._nodes.items()

    def __contains__(self, node_id):
        return node_id in self._nodes

    def __getitem__(self, node_id):
        return self._nodes[node_id]

    def get_file_node_of(self, node_id):
        node = self._nodes[node_id]
        while not node.is_file():
            node = self._nodes[node.scope_id]
        return node

    def _ensure(self, predicate, node_id):
        if not predicate:
            return
        node = self._nodes[node_id]
        if not predicate(node):
            raise AssertionError(
                'not %s: %s' % (predicate.__name__, node.display_name))

    def _get_attachment(self, attachment_name, predicate, node_id):
        self._ensure(predicate, node_id)
        return getattr(self, attachment_name)[node_id]

    def _set_attachment(self, attachment_name, predicate, node_id, value):
        self._ensure(predicate, node_id)
        getattr(self, attachment_name)[node_id] = value

    get_filename = partialmethod(_get_attachment, '_filenames', Node.is_file)
    set_filename = partialmethod(_set_attachment, '_filenames', Node.is_file)

    get_cc_classname = partialmethod(
        _get_attachment, '_cc_classnames', is_struct_or_enum)
    set_cc_classname = partialmethod(
        _set_attachment, '_cc_classnames', is_struct_or_enum)

    get_cython_classname = partialmethod(
        _get_attachment, '_cython_classnames', is_struct_or_enum)
    set_cython_classname = partialmethod(
        _set_attachment, '_cython_classnames', is_struct_or_enum)

    get_python_classname = partialmethod(
        _get_attachment, '_python_classnames', is_struct_or_enum)
    set_python_classname = partialmethod(
        _set_attachment, '_python_classnames', is_struct_or_enum)

    get_cc_reader_member_functions = partialmethod(
        _get_attachment, '_cc_reader_member_functions_table', Node.is_struct)
    set_cc_reader_member_functions = partialmethod(
        _set_attachment, '_cc_reader_member_functions_table', Node.is_struct)

    get_cc_builder_member_functions = partialmethod(
        _get_attachment, '_cc_builder_member_functions_table', Node.is_struct)
    set_cc_builder_member_functions = partialmethod(
        _set_attachment, '_cc_builder_member_functions_table', Node.is_struct)

    get_enum_members = partialmethod(
        _get_attachment, '_enum_members_table', Node.is_enum)
    set_enum_members = partialmethod(
        _set_attachment, '_enum_members_table', Node.is_enum)
