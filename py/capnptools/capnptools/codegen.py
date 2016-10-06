"""Cython code generator."""

__all__ = [
    'generate_cython',
]

import datetime
import warnings
from pathlib import Path

from mako.lookup import TemplateLookup


def generate_cython(node_table, node_ids, pyx_file):

    templates_dir = Path(__file__).parent / 'templates'
    templates = TemplateLookup(directories=[str(templates_dir)])

    pyx_file.write('# Generated at %s - DO NOT EDIT!\n\n' %
                   datetime.datetime.now().isoformat())

    # Generate C++ declarations.

    cppclass_template = templates.get_template('cppclass-declaration.pyx')
    enum_template = templates.get_template('enum-declaration.pyx')

    for node_id in node_ids:
        node = node_table[node_id]

        if node.is_struct() or node.is_enum():
            data = prepare_struct_or_enum_data(node_table, node)
            if node.is_struct():
                template = cppclass_template
            else:
                assert node.is_enum()
                template = enum_template
            pyx_file.write(template.render(**data))

        elif node.is_const():
            warnings.warn('const is not processed at the moment: %s' %
                          node.display_name)
            continue

        else:
            raise AssertionError

        pyx_file.write('\n')


def prepare_struct_or_enum_data(node_table, node):
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
    ]

    # Struct data.
    if node.is_struct():
        getters.extend([
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
            ('enum_members', node_table.get_enum_members, True),
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
