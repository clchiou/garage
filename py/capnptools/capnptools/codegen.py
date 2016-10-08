"""Cython code generator."""

__all__ = [
    'generate_cython',
]

import datetime
from pathlib import Path

from mako.lookup import TemplateLookup


def generate_cython(node_table, node_ids, pyx_file):

    templates_dir = Path(__file__).parent / 'templates'
    templates = TemplateLookup(directories=[str(templates_dir)])

    node_data = {}
    for node_id in node_ids:
        node = node_table[node_id]
        if node.is_struct() or node.is_enum():
            node_data[node_id] = prepare(node_table, node)

    # Generate preamble.

    pyx_file.write(templates.get_template('preamble.pyx').render(
        now=datetime.datetime.now(),
        node_table=node_table,
        list_types=node_table.list_types,
    ))
    pyx_file.write('\n')

    # Generate C++ declarations.

    class_template = templates.get_template('cppclass-declaration.pyx')
    enum_template = templates.get_template('enum-declaration.pyx')

    for node_id in node_ids:
        node = node_table[node_id]

        if node.is_struct():
            pyx_file.write(class_template.render(**node_data[node_id]))

        elif node.is_enum():
            pyx_file.write(enum_template.render(**node_data[node_id]))

        elif node.is_const():
            # 'const' is not processed at the moment.
            continue

        else:
            raise AssertionError

        pyx_file.write('\n')

    # Generate list wrapper classes.

    list_wrapper = templates.get_template('list-wrapper.pyx')
    for list_type in node_table.list_types:
        for level in range(1, list_type.level + 1):
            pyx_file.write(list_wrapper.render(
                node_table=node_table,
                list_type=list_type,
                level=level,
                cython_classname=list_type.get_cython_classname(
                    node_table,
                    level,
                ),
                element_cython_classname=list_type.get_cython_classname(
                    node_table,
                    level - 1,
                ),
                python_classname=list_type.get_python_classname(
                    node_table,
                    level,
                ),
                element_python_classname=list_type.get_python_classname(
                    node_table,
                    level - 1,
                ),
            ))
            pyx_file.write('\n')

    # Generate extension classes.

    class_template = templates.get_template('class-definition.pyx')
    enum_template = templates.get_template('enum-definition.pyx')

    for node_id in node_ids:
        node = node_table[node_id]

        if node.is_struct():
            pyx_file.write(class_template.render(**node_data[node_id]))

        elif node.is_enum():
            pyx_file.write(enum_template.render(**node_data[node_id]))

        elif node.is_const():
            # 'const' is not processed at the moment.
            continue

        else:
            raise AssertionError

        pyx_file.write('\n')

    # Generate message readers.

    struct_nodes = []
    for node_id in node_ids:
        node = node_table[node_id]
        if node.is_struct():
            struct_nodes.append(node)
    pyx_file.write(templates.get_template('message-readers.pyx').render(
        node_table=node_table,
        struct_nodes=struct_nodes,
    ))
    pyx_file.write('\n')


def prepare(node_table, node):
    assert node.is_struct() or node.is_enum()

    # Common data.
    data = {
        'display_name': node.display_name,
        'cc_header': get_cc_header(
            node_table,
            node_table.get_file_node_of(node.id),
        ),
    }
    getters = [
        ('cc_classname', node_table.get_cc_classname, True),
        ('cython_classname', node_table.get_cython_classname, True),
        ('python_classname', node_table.get_python_classname, True),
    ]

    # Struct data.
    if node.is_struct():
        getters.extend([
            ('members', node_table.get_members, False),
            ('cc_reader_member_functions',
             node_table.get_cc_reader_member_functions,
             False),
            ('cc_builder_member_functions',
             node_table.get_cc_builder_member_functions,
             False),
        ])

    # Enum data.
    else:
        assert node.is_enum()
        getters.extend([
            ('members', node_table.get_members, True),
        ])

    for name, getter, required in getters:
        try:
            data[name] = getter(node.id)
        except KeyError:
            if required:
                raise

    return data


def get_cc_header(node_table, file_node):
    filename = node_table.get_filename(file_node.id)
    if filename.startswith('/'):
        return '<%s.h>' % filename[1:]
    else:
        return '%s.h' % filename
