__all__ = [
    'Namespace',
    'Parameter',
    'define',
]

import collections
import io
import json
import logging
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

from startup import startup

from g1.bases import labels
from g1.bases.assertions import ASSERT
from g1.bases.collections import Namespace as _Namespace

from . import bases

LOG = logging.getLogger(__name__)

LABELS = labels.make_labels(
    __name__,
    'parameters',
    'root_namespaces',
    'parameter_table',
)

INITIALIZED = False

# This will be nullified when ``index_root_namespaces`` is called (and
# thus you cannot call ``define`` after that).
ROOT_NAMESPACES = {}

#
# Public interface.
#


def define(module_path, namespace):
    ASSERT.not_none(ROOT_NAMESPACES)
    ASSERT.not_contains(ROOT_NAMESPACES, module_path)
    LOG.debug('define namespace: %s', module_path)
    ROOT_NAMESPACES[module_path] = namespace
    return namespace


class Namespace(_Namespace):

    def __init__(self, _doc=None, **entries):
        #
        # Here are the hacks:
        #
        # * The first positional argument is named ``_doc`` so that (by
        #   convention) it will not name-conflict with keyword argument
        #   names (which should not start with underscore "_").
        #
        # * Because ``_Namespace`` does not allow attribute-setting, we
        #   have to bypass it to set attribute ``_doc``.
        #
        super().__init__(**entries)
        # pylint: disable=bad-super-call
        super(_Namespace, self).__setattr__('_doc', _doc)


class Parameter:

    def __init__(
        self,
        default,
        doc=None,
        type=None,  # pylint: disable=redefined-builtin
        unit=None,
    ):
        self.doc = doc
        self.type = type or default.__class__
        self.unit = unit
        self._value = self.default = self.validate(default)
        self._have_been_read = False

    def validate(self, value):
        return ASSERT.isinstance(value, self.type)

    def get(self):
        """Read parameter value.

        For the ease of writing correct code, a parameter becomes
        immutable once it is read.
        """
        ASSERT.true(INITIALIZED)
        self._have_been_read = True
        return self._value

    def set(self, value):
        ASSERT.false(self._have_been_read)
        self._value = self.validate(value)

    def unsafe_set(self, value):
        """Set parameter value unsafely.

        You should only use this in test code.
        """
        global INITIALIZED
        self._value = value
        INITIALIZED = True


#
# Application startup.
#


@startup
def add_arguments(parser: bases.LABELS.parser) -> bases.LABELS.parse:
    group = parser.add_argument_group(__name__)
    group.add_argument(
        '--parameter-help',
        action='store_true',
        help='list parameters and exit',
    )
    group.add_argument(
        '--parameter-file',
        action='append',
        nargs=2,
        metavar=('FORMAT', 'PATH'),
        help='read parameter values from JSON or YAML file',
    )
    group.add_argument(
        '--parameter',
        action='append',
        nargs=2,
        metavar=('NAME', 'VALUE'),
        help='set parameter value',
    )


@startup
def index_root_namespaces(
    # While this dependency is not really required, let's add it here to
    # sequence this function to called be a little bit later so that you
    # may call ``define`` a little bit late (I am not sure whether this
    # trick is useful, but it is harmless anyway).
    _: bases.LABELS.parse,
) -> (
    LABELS.root_namespaces,
    LABELS.parameter_table,
):
    global ROOT_NAMESPACES
    root_namespaces, ROOT_NAMESPACES = ROOT_NAMESPACES, None
    return (
        root_namespaces,
        {
            label: parameter
            for module_path, namespace in root_namespaces.items()
            for label, parameter in iter_parameters(module_path, namespace)
        },
    )


@startup
def validate_arguments(
    parser: bases.LABELS.parser,
    args: bases.LABELS.args_not_validated,
    root_namespaces: LABELS.root_namespaces,
    parameter_table: LABELS.parameter_table,
) -> bases.LABELS.validate_args:

    if args.parameter_help:
        sys.stdout.write(format_help(root_namespaces))
        sys.exit()

    file_formats = {'json'}
    if yaml:
        file_formats.add('yaml')
    for file_format, path in args.parameter_file or ():
        if file_format.lower() not in file_formats:
            parser.error(
                'unsupported file format for %s: %s (expect: %s)' % (
                    path,
                    file_format,
                    ', '.join(sorted(file_formats)),
                )
            )
        if not Path(path).exists():
            parser.error('parameter file does not exist: %s' % path)

    for name, _ in args.parameter or ():
        if name not in parameter_table:
            parser.error('unrecognized parameter: %s' % name)


@startup
def load_parameters(
    args: bases.LABELS.args,
    root_namespaces: LABELS.root_namespaces,
    parameter_table: LABELS.parameter_table,
) -> LABELS.parameters:

    global INITIALIZED

    loaders = {'json': json.loads}
    if yaml:
        loaders['yaml'] = yaml.safe_load
    for file_format, path in args.parameter_file or ():
        config_forest = loaders[file_format.lower()](Path(path).read_text())
        load_config_forest(config_forest, root_namespaces)

    for name, value_str in args.parameter or ():
        parameter = parameter_table[name]
        # Make a special case for ``str`` type so that you do not have
        # to type extra quotes like '"string"' on command line.
        if (
            isinstance(parameter.type, type)
            and issubclass(parameter.type, str)
        ):
            value = value_str
        else:
            value = json.loads(value_str)
        parameter.set(value)

    INITIALIZED = True


#
# Implementation details.
#


def iter_parameters(module_path, root_namespace):
    parts = collections.deque()

    def do_iter(namespace):
        for name, value in namespace._entries.items():
            parts.append(name)
            if isinstance(value, Namespace):
                yield from do_iter(value)
            else:
                ASSERT.isinstance(value, Parameter)
                label = labels.Label(module_path, '.'.join(parts))
                yield label, value
            parts.pop()

    return do_iter(root_namespace)


def format_help(root_namespaces):

    output = io.StringIO()

    def format_root_namespace(module_path, root_namespace):
        output.write(module_path)
        output.write(':')
        if root_namespace._doc:
            output.write(' ')
            output.write(root_namespace._doc)
        output.write('\n')
        format_namespace(root_namespace, 1)

    def format_namespace(namespace, indent):
        for name, value in namespace._entries.items():
            write_indent(indent)
            output.write(name)
            output.write(':')
            if isinstance(value, Namespace):
                if value._doc:
                    output.write(' ')
                    output.write(value._doc)
                output.write('\n')
                format_namespace(value, indent + 1)
            else:
                ASSERT.isinstance(value, Parameter)
                if value.doc:
                    output.write(' ')
                    output.write(value.doc)
                output.write(' (default: ')
                output.write(json.dumps(value.default))
                if value.unit:
                    output.write(' ')
                    output.write(value.unit)
                output.write(')\n')

    def write_indent(indent):
        for _ in range(indent):
            output.write('    ')

    first = True
    for module_path in sorted(root_namespaces):
        if first:
            first = False
        else:
            output.write('\n')
        format_root_namespace(module_path, root_namespaces[module_path])

    return output.getvalue()


def load_config_forest(config_forest, root_namespaces):

    def load(namespace, config_tree):
        for key, value in ASSERT.isinstance(config_tree, dict).items():
            entry = namespace
            for part in ASSERT.isinstance(key, str).split('.'):
                entry = getattr(entry, part)
            if isinstance(entry, Namespace):
                load(entry, value)
            else:
                ASSERT.isinstance(entry, Parameter)
                entry.set(value)

    for module_path, config_tree in config_forest.items():
        load(root_namespaces[module_path], config_tree)
