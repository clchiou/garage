"""Cap'n Proto Cython compiler plugin"""

__all__ = [
    'main',
]

import datetime
import re
import sys
import warnings
from collections import OrderedDict, defaultdict
from pathlib import Path

from mako.lookup import TemplateLookup

from .schema import CodeGeneratorRequest


def _generate_pyx(request, nodes, root_node, pyx_file):

    ordering = _sort_nodes(nodes, root_node)

    templates_dir = Path(__file__).parent / 'templates'
    templates = TemplateLookup(directories=[str(templates_dir)])

    pyx_file.write('# Generated at %s - DO NOT EDIT!\n\n' %
                   datetime.datetime.now().isoformat())

    # Generate C++ declarations.
    cppclass_template = templates.get_template('cppclass-declaration.pyx')
    enum_template = templates.get_template('enum-declaration.pyx')
    for node in ordering:
        if node.is_struct():
            data = _prepare_cppclass_declaration(node, request, nodes)
            pyx_file.write(cppclass_template.render(
                display_name=node.display_name,
                **data,
            ))
        elif node.is_enum():
            data = _prepare_enum_declaration(node, request, nodes)
            pyx_file.write(enum_template.render(
                display_name=node.display_name,
                **data,
            ))
        elif node.is_const():
            warnings.warn('const is not processed at the moment: %s' %
                          node.display_name)
            continue
        else:
            raise AssertionError
        pyx_file.write('\n')


def _sort_nodes(nodes, root_node):
    """Sort struct, enum, and const nodes in topological order, and
       ignore file, interface, and annotation nodes.
    """
    assert root_node.is_file()

    reachable, dependencies, reverse_dependencies = \
        _compute_graph(nodes, root_node)

    # Do topology sort.
    ordering = []
    input_order = {node_id: index for index, node_id in enumerate(nodes)}
    queue = [
        # Iterate over `nodes` to preserve input order.
        node_id for node_id in nodes
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

    return [nodes[node_id] for node_id in ordering]


def _compute_graph(nodes, root_node):

    # Filter out unreachable nodes.
    reachable = set()

    # Construct dependency graph.
    dependencies = defaultdict(set)

    queue = [nested_node.id for nested_node in root_node.nested_nodes or ()]
    while queue:
        node_id = queue.pop()
        if node_id in reachable:
            continue
        node = nodes[node_id]
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


def _prepare_cppclass_declaration(struct_node, request, nodes):
    assert struct_node.is_struct()

    data = {}

    parent_nodes = _get_parent_nodes(struct_node, nodes)
    assert parent_nodes

    file_node = parent_nodes[-1]
    assert file_node.is_file()

    data['cc_header'] = _get_cc_header(file_node, request)

    cc_namespace = _get_cc_namespace(file_node, nodes)
    if cc_namespace is not None:
        data['cc_namespace'] = cc_namespace
        data['py_namespace'] = cc_namespace.replace('::', '__')

    class_name_comps = _get_class_name_components(struct_node, parent_nodes)
    class_name_comps.reverse()
    data['cc_class'] = '::'.join(class_name_comps)
    data['py_class'] = '__'.join(class_name_comps)

    return data


def _prepare_enum_declaration(enum_node, request, nodes):
    assert enum_node.is_enum()

    data = {}

    parent_nodes = _get_parent_nodes(enum_node, nodes)
    assert parent_nodes

    file_node = parent_nodes[-1]
    assert file_node.is_file()

    data['cc_header'] = _get_cc_header(file_node, request)

    cc_namespace = _get_cc_namespace(file_node, nodes)
    if cc_namespace is not None:
        data['cc_namespace'] = cc_namespace
        data['py_namespace'] = cc_namespace.replace('::', '__')

    class_name_comps = _get_class_name_components(enum_node, parent_nodes)
    class_name_comps.reverse()
    data['cc_enum'] = '::'.join(class_name_comps)
    data['py_enum'] = '__'.join(class_name_comps)

    data['cc_enum_members'] = [
        _camel_case_to_upper_snake_case(enumerant.name)
        for enumerant in enum_node.enumerants
    ]

    return data


def _get_parent_nodes(node, nodes):
    parents = []
    while node.scope_id != 0:
        node = nodes[node.scope_id]
        parents.append(node)
    return parents


def _get_cc_header(file_node, request):
    assert file_node.is_file()
    filename = None
    for requested_file in request.requested_files:
        if requested_file.id == file_node.id:
            filename = requested_file.filename
            break
        for import_ in requested_file.imports:
            if import_.id == file_node.id:
                filename = import_.name
                break
        if filename is not None:
            break
    if filename is None:
        raise ValueError('no filename found for %s' % file_node.display_name)
    if filename.startswith('/'):
        return '<%s.h>' % filename[1:]
    else:
        return '%s.h' % filename


def _get_cc_namespace(file_node, nodes):
    assert file_node.is_file()
    for annotation in file_node.annotations or ():
        if _is_namespace_annotation(annotation, nodes):
            return annotation.value.text
    return None


def _is_namespace_annotation(annotation, nodes):
    annotation_node = nodes[annotation.id]
    parent = nodes[annotation_node.scope_id]
    for nested_node in parent.nested_nodes or ():
        if (nested_node.id == annotation_node.id and
                nested_node.name == 'namespace'):
            return True
    return False


def _get_class_name_components(current_node, parent_nodes):
    # It works somewhat backward but you have to look up current_node's
    # name from its parent.
    class_name_comps = []
    for parent_node in parent_nodes:
        name = None
        # Nested struct.
        if (parent_node.is_file() or
                (current_node.is_struct() and not current_node.is_group())):
            for nested_node in parent_node.nested_nodes or ():
                if nested_node.id == current_node.id:
                    name = nested_node.name
                    break
        # Group field (not really an independent struct).
        elif current_node.is_struct() and current_node.is_group():
            for field in parent_node.fields or ():
                if field.is_group() and field.type_id == current_node.id:
                    name = _camel_case_to_upper(field.name)
                    break
        # Enum.
        elif current_node.is_enum():
            for field in parent_node.fields or ():
                if (field.is_slot() and
                        field.type.is_enum() and
                        field.type.type_id == current_node.id):
                    name = _camel_case_to_upper(field.name)
                    break
        if name is None:
            raise ValueError(
                'no class name component for %s in %s' %
                (current_node.display_name, parent_node.display_name))
        class_name_comps.append(name)
        current_node = parent_node
    return class_name_comps


def _camel_case_to_upper(lower_camel):
    """Turn "camelCase" into "CamelCase"."""
    return '%s%s' % (lower_camel[0].upper(), lower_camel[1:])


def _camel_case_to_upper_snake_case(camel):
    # NOTE: This would also turn "CAMEL" into "C_A_M_E_L".
    return ('%s%s' % (camel[0], re.sub(r'([A-Z])', r'_\1', camel[1:]))).upper()


def main():
    request = CodeGeneratorRequest(sys.stdin.buffer.read())

    if not request.nodes:
        raise ValueError('no node in code generator request')
    nodes = OrderedDict((node.id, node) for node in request.nodes)

    if not request.requested_files:
        raise ValueError('no requested file')

    # At the moment we can't handle more than one requested file.
    if len(request.requested_files) > 1:
        raise ValueError('more than one requested files')
    requested_file = request.requested_files[0]

    if not requested_file.filename:
        raise ValueError('no filename in requested file')
    pyx_path = Path(requested_file.filename).with_suffix('.pyx')

    pyx_path.parent.mkdir(parents=True, exist_ok=True)
    with pyx_path.open('w') as pyx_file:
        _generate_pyx(request, nodes, nodes[requested_file.id], pyx_file)


if __name__ == '__main__':
    main()
