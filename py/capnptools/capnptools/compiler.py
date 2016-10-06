"""Cap'n Proto Cython compiler plugin"""

__all__ = [
    'main',
]

import sys
from collections import defaultdict
from pathlib import Path

from .analyzers import analyze_nodes
from .codegen import generate_cython
from .schema import CodeGeneratorRequest
from .tables import NodeTable


### Find and sort nodes.


def filter_and_sort_nodes(node_table, root_node_id):
    """Sort struct, enum, and const nodes in topological order, and
       ignore file, interface, and annotation nodes.
    """

    reachable, dependencies, reverse_dependencies = \
        compute_graph(node_table, root_node_id)

    # Do topology sort.
    ordering = []
    input_order = {node_id: index for index, node_id in enumerate(node_table)}
    queue = [
        # Iterate over `node_table` to preserve input order.
        node_id for node_id in node_table
        if node_id in reachable and not dependencies[node_id]
    ]
    while queue:
        node_id = queue.pop()
        ordering.append(node_id)
        more_node_ids = []
        for rdep in reverse_dependencies[node_id]:
            deps = dependencies[rdep]
            deps.remove(node_id)
            if not deps:
                more_node_ids.append(rdep)
        # Sort node_id by the input order.
        more_node_ids.sort(key=lambda node_id: input_order[node_id])
        queue.extend(more_node_ids)
    # All reachable nodes should all be ordered.
    assert len(ordering) == len(reachable)

    return ordering


def compute_graph(node_table, root_node_id):

    # Filter out unreachable nodes.
    reachable = set()

    # Construct dependency graph.
    dependencies = defaultdict(set)

    root_node = node_table[root_node_id]
    queue = [nested_node.id for nested_node in root_node.nested_nodes or ()]
    while queue:
        node_id = queue.pop()
        if node_id in reachable:
            continue
        node = node_table[node_id]
        if not (node.is_struct() or node.is_enum() or node.is_const()):
            continue
        reachable.add(node_id)
        if node.is_struct():
            for field in node.fields or ():
                type_id = None
                if field.is_slot():
                    assert field.type is not None
                    type_ = field.type
                    while type_.is_list():
                        type_ = type_.element_type
                    if type_.is_enum() or type_.is_struct():
                        type_id = type_.type_id
                else:
                    assert field.is_group()
                    type_id = field.type_id
                if type_id is not None:
                    dependencies[node_id].add(type_id)
                    queue.append(type_id)

    reverse_dependencies = {node_id: set() for node_id in reachable}
    for node_id, deps in dependencies.items():
        for dep in deps:
            reverse_dependencies[dep].add(node_id)

    return reachable, dependencies, reverse_dependencies


### Main.


def main():
    request = CodeGeneratorRequest(sys.stdin.buffer.read())

    if not request.nodes:
        raise ValueError('no node in code generator request')
    node_table = NodeTable(request.nodes)

    if not request.requested_files:
        raise ValueError('no requested file')

    # At the moment we can't handle more than one requested file.
    if len(request.requested_files) > 1:
        raise ValueError('more than one requested files')
    requested_file = request.requested_files[0]

    if not requested_file.filename:
        raise ValueError('no filename in requested file')
    pyx_path = Path(requested_file.filename).with_suffix('.pyx')

    node_ids = filter_and_sort_nodes(node_table, requested_file.id)

    for node_id, node in node_table.items():
        if node.is_file():
            node_table.set_filename(node_id, find_filename(node, request))

    analyze_nodes(node_table, node_ids)

    pyx_path.parent.mkdir(parents=True, exist_ok=True)
    with pyx_path.open('w') as pyx_file:
        generate_cython(node_table, node_ids, pyx_file)


def find_filename(file_node, request):
    assert file_node.is_file()
    for requested_file in request.requested_files:
        if requested_file.id == file_node.id:
            return requested_file.filename
        for import_ in requested_file.imports:
            if import_.id == file_node.id:
                return import_.name
    raise ValueError('cannot find filename for %s' % file_node.display_name)


if __name__ == '__main__':
    main()
