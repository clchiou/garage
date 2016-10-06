"""Look up code generation info and store it into node_table."""

__all__ = [
    'analyze_nodes',
]

import re
import warnings
from collections import namedtuple


Function = namedtuple('Function', [
    'name',
    'return_type',
    'parameters',
    'suffix',
])


def analyze_nodes(node_table, node_ids):
    """Look up code generation info and store it into node_table."""

    # First pass.
    for node_id in node_ids:
        node = node_table[node_id]

        if node.is_struct() or node.is_enum():

            cc_namespace = find_cc_namespace(node_table, node)
            comps = get_class_name_components(node_table, node)
            comps.reverse()
            classname = '::'.join(comps)
            if cc_namespace:
                classname = '%s::%s' % (cc_namespace, classname)
            node_table.set_cc_classname(node_id, classname)
            node_table.set_cython_classname(
                node_id, classname.replace('::', '__'))

            if node.is_enum():
                enum_members = [
                    camel_case_to_upper_snake_case(enumerant.name)
                    for enumerant in node.enumerants
                ]
                node_table.set_enum_members(node_id, enum_members)

        elif node.is_const():
            warnings.warn('const is not processed at the moment: %s' %
                          node.display_name)

        else:
            raise AssertionError

    # Second pass.  Here we may refer to results of the first pass.
    for node_id in node_ids:
        node = node_table[node_id]
        if node.is_struct():
            analyze_struct(node_table, node)


def find_cc_namespace(node_table, node):
    assert node.is_struct() or node.is_enum()
    file_node = node_table.get_file_node_of(node.id)
    for annotation in file_node.annotations or ():
        if is_namespace_annotation(node_table, annotation):
            return annotation.value.text
    return None


def is_namespace_annotation(node_table, annotation):
    annotation_node = node_table[annotation.id]
    parent = node_table[annotation_node.scope_id]
    for nested_node in parent.nested_nodes or ():
        if (nested_node.id == annotation_node.id and
                nested_node.name == 'namespace'):
            return True
    return False


def get_class_name_components(node_table, current_node):

    # It works somewhat backward but you have to look up current_node's
    # name from its parent.

    class_name_comps = []

    while not current_node.is_file():
        parent_node = node_table[current_node.scope_id]

        name = None

        # Normal struct.
        if current_node.is_struct() and not current_node.is_group():
            for nested_node in parent_node.nested_nodes or ():
                if nested_node.id == current_node.id:
                    name = nested_node.name
                    break

        # Group field (not really an independent struct).
        elif current_node.is_struct() and current_node.is_group():
            for field in parent_node.fields or ():
                if field.is_group() and field.type_id == current_node.id:
                    name = camel_case_to_upper(field.name)
                    break

        # Enum.
        elif current_node.is_enum():
            for field in parent_node.fields or ():
                if (field.is_slot() and
                        field.type.is_enum() and
                        field.type.type_id == current_node.id):
                    name = camel_case_to_upper(field.name)
                    break

        if name is None:
            raise ValueError(
                'no class name component for %s in %s' %
                (current_node.display_name, parent_node.display_name))

        class_name_comps.append(name)
        current_node = parent_node

    assert class_name_comps

    return class_name_comps


### Analyze structs.


def analyze_struct(node_table, struct_node):
    assert struct_node.is_struct()

    cc_reader = []
    cc_builder = []

    for field in struct_node.fields or ():

        name = camel_case_to_upper(field.name)
        izzer = 'is%s' % name
        hazzer = 'has%s' % name
        getter = 'get%s' % name
        setter = 'set%s' % name
        initer = 'init%s' % name

        if field.is_slot():

            reader_field_type_name = make_reader_type_name(
                node_table, field.type)
            builder_field_type_name = make_builder_type_name(
                node_table, field.type)

            # izzer
            if struct_node.is_group():
                cc_reader.append(Function(
                    name=izzer,
                    return_type='bool',
                    parameters=(),
                    suffix='const except +',
                ))
                cc_builder.append(Function(
                    name=izzer,
                    return_type='bool',
                    parameters=(),
                    suffix='except +',
                ))

            # hazzer
            if is_pointer_type(field.type):
                cc_reader.append(Function(
                    name=hazzer,
                    return_type='bool',
                    parameters=(),
                    suffix='const except +',
                ))
                cc_builder.append(Function(
                    name=hazzer,
                    return_type='bool',
                    parameters=(),
                    suffix='except +',
                ))

            # getter
            if not field.type.is_void():
                cc_reader.append(Function(
                    name=getter,
                    return_type=reader_field_type_name,
                    parameters=(),
                    suffix='const except +',
                ))
                cc_builder.append(Function(
                    name=getter,
                    return_type=builder_field_type_name,
                    parameters=(),
                    suffix='except +',
                ))

            # setter
            cc_builder.append(Function(
                name=setter,
                return_type='void',
                parameters=(
                    [] if field.type.is_void() else [builder_field_type_name]
                ),
                suffix='except +',
            ))

            # initer
            if is_pointer_type(field.type):
                cc_builder.append(Function(
                    name=initer,
                    return_type=builder_field_type_name,
                    parameters=(),
                    suffix='except +',
                ))

        else:
            assert field.is_group()

            # getter
            cc_reader.append(Function(
                name=getter,
                return_type=(
                    '%s__Reader' %
                    node_table.get_cython_classname(field.type_id)
                ),
                parameters=(),
                suffix='const except +',
            ))
            cc_builder.append(Function(
                name=getter,
                return_type=(
                    '%s__Builder' %
                    node_table.get_cython_classname(field.type_id)
                ),
                parameters=(),
                suffix='except +',
            ))

            # initer
            cc_builder.append(Function(
                name=initer,
                return_type=(
                    '%s__Builder' %
                    node_table.get_cython_classname(field.type_id)
                ),
                parameters=(),
                suffix='except +',
            ))

    if cc_reader:
        node_table.set_cc_reader_member_functions(struct_node.id, cc_reader)
    if cc_builder:
        node_table.set_cc_builder_member_functions(struct_node.id, cc_builder)


def is_pointer_type(type_):
    return (
        type_.is_text() or
        type_.is_data() or
        type_.is_list() or
        type_.is_struct()
    )


def make_reader_type_name(node_table, type_):
    type_name = _make_type_name(node_table, type_)
    if is_pointer_type(type_):
        type_name = '%s__Reader' % type_name
    return type_name


def make_builder_type_name(node_table, type_):
    type_name = _make_type_name(node_table, type_)
    if is_pointer_type(type_):
        type_name = '%s__Builder' % type_name
    return type_name


def _make_type_name(node_table, type_):
    if type_.is_void():
        return 'capnp__Void'
    elif type_.is_primitive():
        return type_.primitive_type_name
    elif type_.is_text():
        return 'capnp__Text'
    elif type_.is_data():
        return 'capnp__Data'
    elif type_.is_list():
        return 'List__%s' % _make_type_name(node_table, type_.element_type)
    elif type_.is_enum():
        return node_table.get_cython_classname(type_.type_id)
    elif type_.is_struct():
        return node_table.get_cython_classname(type_.type_id)
    else:
        raise AssertionError


### Analyzer helpers.


def camel_case_to_upper(lower_camel):
    """Turn "camelCase" into "CamelCase"."""
    return '%s%s' % (lower_camel[0].upper(), lower_camel[1:])


def camel_case_to_upper_snake_case(camel):
    # NOTE: This would also turn "CAMEL" into "C_A_M_E_L".
    return _camel_case_to_snake_case(camel).upper()


def camel_case_to_lower_snake_case(camel):
    # NOTE: This would also turn "CAMEL" into "c_a_m_e_l".
    return _camel_case_to_snake_case(camel).lower()


def _camel_case_to_snake_case(camel):
    return '%s%s' % (camel[0], re.sub(r'([A-Z])', r'_\1', camel[1:]))
