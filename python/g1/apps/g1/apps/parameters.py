"""Parameters and hierarchy of parameter namespaces.

This module provides:

* A global registry of parameters (I am not sure whether this is a good
  or bad design, but it is quite useful at the moment).
* Parameters are grouped by namespaces, and namespaces are organized in
  a global hierarchy.
* Names (i.e., labels) that are globally unique to reference all
  parameters.
* Parameter values are loaded-able from command-line arguments and from
  parameter value files (JSON or YAML formatted).

We impose some restrictions on the exposed interface.  These are design
choices that we think may be good for now, and we might revisit these
restrictions if we have good use cases against these restrictions.

* Parameters should have a functional default value (i.e., not None nor
  some dummy values).  In most use cases your application should be
  using the default values, or in other words, your user do not need to
  provide parameter values (through command-line or parameter value
  files) in most use cases.  If a parameter does not have a functional
  default value in most use cases, maybe you should make it an explicit
  command-line argument.

* We do not expect concurrent read and write of parameter values, and we
  provide no protection for concurrency at the moment.  We assume that
  in (almost) all use cases, parameter values are loaded during program
  startup (serially, not concurrently) and unchanged throughout the
  entire lifetime of the process.

* Parameters do not provide on-change callback; to prevent unintentional
  write after read, parameters become immutable after the first read.

* We do not load parameter values from environment variables as in
  general we prefer explicit over implicit sources of parameter values.

As to how to make a parameter object, here is the rule of thumb:

* If a parameter cannot have a default value, use RequiredParameter.
* If a parameter's default value is static, use Parameter.  Also you
  don't need to pass the type parameter.
* If a parameter's default value can be overridden by user, use
  Parameter with an explicit type parameter.
* If user may choose not to provide a default value to a parameter, use
  make_parameter.
* If a parameter's value is constant, use ConstParameter.
"""

__all__ = [
    # Namespace.
    'Namespace',
    'define',
    # Parameter.
    'ConstParameter',
    'Parameter',
    'RequiredParameter',
    'make_parameter',
]

import argparse
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


class ParameterBase:

    def __init__(
        self,
        *,
        type=None,  # pylint: disable=redefined-builtin
        doc=None,
        convert=None,
        validate=None,
        format=None,  # pylint: disable=redefined-builtin
        unit=None,
    ):
        self.type = type
        self.doc = doc
        self.convert = convert
        self.validate = validate
        self.format = format
        self.unit = unit
        self._value = None
        self._have_been_read = False

    def _validate(self, value):
        ASSERT.isinstance(value, self.type)
        if self.validate:
            ASSERT.predicate(value, self.validate)
        return value

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
        self._value = self._validate(value)

    def unsafe_set(self, value):
        """Set parameter value unsafely.

        You should only use this in test code.
        """
        global INITIALIZED
        self._value = value
        INITIALIZED = True


class Parameter(ParameterBase):

    def __init__(self, default, doc=None, **kwargs):
        """Make a parameter.

        * type is default to default value's type, and set() will check
          new parameter value's type.
        * convert is used by the parameter value loader to convert the
          "raw" value.  Note that raw value might not be string-typed.
        * validate is an optional validation function (in addition to
          the type check).
        # format is for producing help text.  It does NOT have to be
          inverse of convert.
        """
        kwargs.setdefault('type', type(default))
        super().__init__(doc=doc, **kwargs)
        self._value = self.default = self._validate(default)


class ConstParameter(ParameterBase):

    def __init__(self, value, doc=None, **kwargs):
        kwargs.setdefault('type', type(value))
        super().__init__(doc=doc, **kwargs)
        self._value = self.value = self._validate(value)

    def set(self, value):
        ASSERT.unreachable('cannot set to a const parameter: {}', value)


class RequiredParameter(ParameterBase):
    """Parameter that user is required to explicitly set its value.

    Use this class as an exception rather than a norm.  If you find that
    you use this class a lot in an application, you might want to
    redesign that application.
    """

    def __init__(self, type, doc=None, **kwargs):  # pylint: disable=redefined-builtin
        ASSERT.is_not(type, None.__class__)
        super().__init__(type=type, doc=doc, **kwargs)

    def get(self):
        ASSERT.not_none(self._value)
        return super().get()


def make_parameter(default, type, doc=None, **kwargs):  # pylint: disable=redefined-builtin
    """Make a parameter object.

    If default is None, it will make a RequiredParameter object.
    """
    if default is None:
        return RequiredParameter(type, doc, **kwargs)
    else:
        return Parameter(default, doc, type=type, **kwargs)


#
# Application startup.
#


class ParameterHelpAction(argparse.Action):

    def __init__(
        self,
        option_strings,
        dest=argparse.SUPPRESS,
        default=argparse.SUPPRESS,
        help=None,  # pylint: disable=redefined-builtin
    ):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        sys.stdout.write(format_help(ROOT_NAMESPACES))
        parser.exit()


@startup
def add_arguments(parser: bases.LABELS.parser) -> bases.LABELS.parse:
    group = parser.add_argument_group(__name__)
    group.add_argument(
        '--parameter-help',
        action=ParameterHelpAction,
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
    parameter_table: LABELS.parameter_table,
) -> bases.LABELS.validate_args:

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
        file_format = file_format.lower()
        loader = loaders[file_format]
        path = Path(path)
        if path.is_dir():
            paths = sorted(
                p for p in path.glob('*.%s' % file_format) if p.is_file()
            )
        else:
            paths = [path]
        for p in paths:
            config_forest = loader(p.read_bytes())
            load_config_forest(config_forest, root_namespaces)

    for name, value_str in args.parameter or ():
        parameter = parameter_table[name]
        # Make a special case for str and Path type so that you do not
        # have to type extra quotes like '"string"' on command line.
        if (
            isinstance(parameter.type, type)
            and issubclass(parameter.type, (str, Path))
        ):
            value = value_str
        else:
            value = json.loads(value_str)
        if parameter.convert:
            value = parameter.convert(value)
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
                ASSERT.isinstance(value, ParameterBase)
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

    def format_parameter_info(value):
        output_parts = []
        
        if value.doc:
            output_parts.append(' ' + value.doc)
            
        if isinstance(value, Parameter):
            output_parts.append(' (default: ' + (value.format or json.dumps)(value.default))
        elif isinstance(value, ConstParameter):
            output_parts.append(' (value: ' + (value.format or json.dumps)(value.value))
        else:
            ASSERT.isinstance(value, RequiredParameter)
            if isinstance(value.type, type):
                type_str = value.type.__name__
            else:
                type_str = ', '.join(t.__name__ for t in value.type)
            output_parts.append(' (type: ' + type_str)
            
        if value.unit:
            if isinstance(value, RequiredParameter):
                output_parts.append(', unit: ' + value.unit)
            else:
                output_parts.append(' ' + value.unit)
                
        output_parts.append(')')
        return ''.join(output_parts)

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
                ASSERT.isinstance(value, ParameterBase)
                output.write(format_parameter_info(value))
                output.write('\n')


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
                ASSERT.isinstance(entry, ParameterBase)
                if entry.convert:
                    value = entry.convert(value)
                entry.set(value)

    for module_path, config_tree in config_forest.items():
        load(root_namespaces[module_path], config_tree)
