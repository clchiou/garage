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


class Member:

    def __init__(self, node_table, struct_node, field):
        assert struct_node.is_struct()

        self.name = camel_case_to_lower_snake_case(field.name)

        name = camel_case_to_upper(field.name)
        izzer = 'is%s' % name
        hazzer = 'has%s' % name
        getter = 'get%s' % name
        setter = 'set%s' % name
        initer = 'init%s' % name

        if field.is_slot():

            self.type_name = make_type_name(node_table, field.type, True)
            self.cython_type_name = make_type_name(
                node_table, field.type, False)

            self.is_void = field.type.is_void()
            self.is_primitive = field.type.is_primitive()
            self.is_text = field.type.is_text()
            self.is_data = field.type.is_data()
            self.is_list = field.type.is_list()
            self.is_enum = field.type.is_enum()
            self.is_struct = field.type.is_struct()

            self.izzer = izzer  if struct_node.is_group() else None
            self.hazzer = hazzer if is_pointer(field.type) else None
            self.getter = getter if not self.is_void else None
            self.setter = setter
            self.initer = initer if is_pointer(field.type) else None

        else:
            assert field.is_group()

            self.type_name = node_table.get_python_classname(field.type_id)
            self.cython_type_name = node_table.get_cython_classname(
                field.type_id)

            self.is_void = False
            self.is_primitive = False
            self.is_text = False
            self.is_data = False
            self.is_list = False
            self.is_enum = False
            self.is_struct = True

            self.izzer = None
            self.hazzer = None
            self.getter = getter
            self.setter = None
            self.initer = initer


class ListType:

    def __init__(self, type_):
        if not type_.is_list():
            raise ValueError('not list type: %r' % type_)
        self.level = 0
        while type_.is_list():
            type_ = type_.element_type
            self.level += 1
        assert self.level > 0
        if type_.is_void():
            self.base_type = ('v', None)
        elif type_.is_primitive():
            self.base_type = ('p', type_.primitive_type_name())
        elif type_.is_text():
            self.base_type = ('t', None)
        elif type_.is_data():
            self.base_type = ('d', None)
        elif type_.is_enum():
            self.base_type = ('e', type_.type_id)
        elif type_.is_struct():
            self.base_type = ('s', type_.type_id)
        else:
            raise AssertionError

    def __eq__(self, other):
        return self.level == other.level and self.base_type == other.base_type

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self.level, self.base_type))

    def get_cc_classname(self, node_table):
        if self.base_type[0] == 'v':
            type_name = 'capnp::Void'
        elif self.base_type[0] == 'p':
            type_name = self.base_type[1]
        elif self.base_type[0] == 't':
            type_name = 'capnp::Text'
        elif self.base_type[0] == 'd':
            type_name = 'capnp::Data'
        elif self.base_type[0] in ('e', 's'):
            type_name = node_table.get_cc_classname(self.base_type[1])
        else:
            raise AssertionError
        return ('%s%s%s' %
                ('capnp::List<' * self.level, type_name, '>' * self.level))

    def get_cython_classname(self, node_table):
        if self.base_type[0] == 'v':
            type_name = 'capnp__Void'
        elif self.base_type[0] == 'p':
            type_name = self.base_type[1]
        elif self.base_type[0] == 't':
            type_name = 'capnp__Text'
        elif self.base_type[0] == 'd':
            type_name = 'capnp__Data'
        elif self.base_type[0] in ('e', 's'):
            type_name = node_table.get_cython_classname(self.base_type[1])
        else:
            raise AssertionError
        return '%s%s' % ('List__' * self.level, type_name)


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

            classname = classname.replace('::', '__')
            node_table.set_cython_classname(node_id, '_cc__' + classname)
            node_table.set_python_classname(node_id, classname)

            if node.is_struct():
                for field in node.fields or ():
                    if field.is_slot() and field.type.is_list():
                        node_table.add_list_type(ListType(field.type))

            else:
                assert node.is_enum()
                members = [
                    camel_case_to_upper_snake_case(enumerant.name)
                    for enumerant in node.enumerants
                ]
                node_table.set_members(node_id, members)

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
            members = [
                Member(node_table, node, field)
                for field in node.fields or ()
            ]
            node_table.set_members(node_id, members)


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

        # NOTE: At the moment, Cython does not accept 'const except +'
        # in member function declaration, but 'const' suffix doesn't
        # really provide any value to Cython anyway.

        if field.is_slot():

            reader_field_type_name = make_reader_type_name(
                node_table, field.type, False)
            builder_field_type_name = make_builder_type_name(
                node_table, field.type, False)

            # izzer
            if struct_node.is_group():
                cc_reader.append(Function(
                    name=izzer,
                    return_type='bool',
                    parameters=(),
                    suffix='except +',
                ))
                cc_builder.append(Function(
                    name=izzer,
                    return_type='bool',
                    parameters=(),
                    suffix='except +',
                ))

            # hazzer
            if is_pointer(field.type):
                cc_reader.append(Function(
                    name=hazzer,
                    return_type='bool',
                    parameters=(),
                    suffix='except +',
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
                    suffix='except +',
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
            if is_pointer(field.type):
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
                suffix='except +',
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


def is_pointer(type_):
    return (
        type_.is_text() or
        type_.is_data() or
        type_.is_list() or
        type_.is_struct()
    )


def make_reader_type_name(node_table, type_, use_python_classname):
    type_name = make_type_name(node_table, type_, use_python_classname)
    if is_pointer(type_):
        type_name = '%s__Reader' % type_name
    return type_name


def make_builder_type_name(node_table, type_, use_python_classname):
    type_name = make_type_name(node_table, type_, use_python_classname)
    if is_pointer(type_):
        type_name = '%s__Builder' % type_name
    return type_name


def make_type_name(node_table, type_, use_python_classname):
    if type_.is_void():
        return 'capnp__Void'
    elif type_.is_primitive():
        return type_.primitive_type_name
    elif type_.is_text():
        return 'capnp__Text'
    elif type_.is_data():
        return 'capnp__Data'
    elif type_.is_list():
        return 'List__%s' % make_type_name(
            node_table, type_.element_type, use_python_classname)
    elif type_.is_enum():
        if use_python_classname:
            return node_table.get_python_classname(type_.type_id)
        else:
            return node_table.get_cython_classname(type_.type_id)
    elif type_.is_struct():
        if use_python_classname:
            return node_table.get_python_classname(type_.type_id)
        else:
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
