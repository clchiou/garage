"""Parameters.

The use case of the `parameters` module is for module-level, (mostly)
read-only parameters.  The parameter values are read from two sources,
higher precedence one comes first:
  * Command-line arguments.
  * Configuration files.

Parameters are grouped by a (hierarchy of) namespaces.

For now, parameters have a few deliberately-made design constraints:
  * It only supports scalar parameter value types, and does not provide
    interface for adding custom parameter types.
  * It does not read parameter values from the environment because:
    * Environment variables are not explicit, and we might unwittingly
      override a parameter.
    * It looks like command-ling arguments and configuration files may
      cover all use cases.
We might loose these constraints later after we try more use cases.
"""

__all__ = [
    'define',
    'define_namespace',
    'get',
]

import enum
import json
import logging
from collections import OrderedDict
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

from garage.assertions import ASSERT


LOG = logging.getLogger(__name__)


def _assert_parameter_name(name):
    ASSERT(
        not name.startswith('_'),
        'expect parameter name not start with underscore: %r', name,
    )
    return name


# The real namespace that Namespace is as a proxy for.
class ParameterNamespace:
    """Collection of parameters.

    For each module that you want to define parameters in, you collect
    them in a parameter namespace (which can be nested).

    Although it is possible to design the parameters interface without
    namespaces, it is easier to manage the parameters where they are
    grouped by namespaces.
    """

    def __init__(self, doc=None):
        self.doc = doc
        self.parameters = OrderedDict()

    def items(self):
        return self.parameters.items()

    def __iter__(self):
        yield from self.parameters.keys()

    def __getitem__(self, name):
        return self.parameters[name]

    def __setitem__(self, name, parameter):
        ASSERT.type_of(parameter, (ParameterNamespace, Parameter))
        ASSERT.not_in(name, self.parameters)  # Forbid overriding.
        self.parameters[name] = parameter


# This is a proxy for the actual namespace; it mainly lets user access
# parameters through attributes (for convenience).
class Namespace:

    def __init__(self, namespace):
        super().__setattr__('_namespace', namespace)

    def __getattr__(self, name):
        try:
            parameter = self._namespace[_assert_parameter_name(name)]
        except KeyError:
            raise AttributeError('parameter is not found: %s' % name) from None
        if isinstance(parameter, ParameterNamespace):
            # Wrap a namespace in a proxy object.
            parameter = Namespace(parameter)
        return parameter

    def __setattr__(self, name, parameter):
        if isinstance(parameter, Namespace):
            # Unwrap a proxy object.
            parameter = parameter._namespace
        self._namespace[_assert_parameter_name(name)] = parameter


Namespace.__doc__ = ParameterNamespace.__doc__


class ParameterDescriptor:
    """Abstract parameter descriptor interface."""

    def parse(self, value_str):
        """Parse parameter value from its string form, and raise when
        value_str is ill-formed.
        """
        raise NotImplementedError

    def validate(self, value):
        """Raise on invalid parameter value."""
        raise NotImplementedError

    def add_argument_to(self, flag, parameter, parser):
        """Add parameter to an argparse.ArgumentParser object."""
        raise NotImplementedError


class SimpleParameterDescriptor(ParameterDescriptor):

    def __init__(self, type, *, parse=None, show=str, metavar=None):
        self._type = type
        self._parse = parse or type
        self._show = show
        self._metavar = metavar or self._type.__name__.upper()

    def parse(self, value_str):
        return self._parse(value_str)

    def validate(self, value):
        ASSERT.type_of(value, self._type)

    def add_argument_to(self, flag, parameter, parser):
        doc = parameter.doc
        if doc is None:
            doc = 'default: %s' % self._show(parameter.default)
        else:
            doc = '%s (default: %s)' % (doc, self._show(parameter.default))
        # Do not provide parameter.default to parser.add_argument as we
        # check `args.var_name is None` at later point to know whether
        # a parameter is overridden from command-line.
        parser.add_argument(
            flag,
            type=self._parse,
            metavar=self._metavar,
            help=doc,
        )


class Parameter:
    """Represent a parameter.

    The current design requires that a parameter always has a default
    value, with the assumption that most of the time, the majority of
    parameter values will not be overridden, and thus they are required
    to have a default value.
    """

    def __init__(self, descriptor, default, doc):
        descriptor.validate(default)
        self.default = default
        self.doc = doc
        self.descriptor = descriptor
        self._value = default
        self._have_been_read = False

    def get(self):
        self._have_been_read = True
        return self._value

    def set(self, value):
        """Set parameter value.

        For code correctness, once a parameter has been read, it
        basically becomes immutable, for the reason that the code once
        read it may not read it again for the new value.
        """
        ASSERT.false(self._have_been_read)
        self.unsafe_set(value)

    def unsafe_set(self, value):
        """Set parameter value unsafely.

        You should only use this in test code.
        """
        self.descriptor.validate(value)
        self._value = value


# Collection of module-level ParameterNamespace objects.
_ROOT_NAMESPACE = ParameterNamespace()


def get(module_name, doc=None):
    """Get (module-level) parameter namespace."""
    return _get_or_make_namespace(_ROOT_NAMESPACE, module_name, doc)


def _get_or_make_namespace(root_namespace, module_name, doc):
    if module_name == '__main__':
        return Namespace(root_namespace)
    try:
        namespace = root_namespace[module_name]
    except KeyError:
        root_namespace[module_name] = namespace = ParameterNamespace(doc)
    return Namespace(namespace)


_PARAMETER_DESCRIPTORS = {
    bool: SimpleParameterDescriptor(
        type=bool,
        parse=(lambda value_str:
               ASSERT.in_(value_str, ('true', 'false')) == 'true'),
        show=lambda value: 'true' if value else 'false',
        metavar='{true,false}',
    ),
    float: SimpleParameterDescriptor(float),
    int: SimpleParameterDescriptor(int),
    str: SimpleParameterDescriptor(str, show=repr),
    Path: SimpleParameterDescriptor(Path),
}


def define_namespace(doc=None):
    """Define a parameter (sub-)namespace."""
    return Namespace(ParameterNamespace(doc))


def define(default, doc=None, type=None):
    """Define a parameter.

    The parameter type is inferred from the default value unless
    overridden.
    """
    return _define_parameter(_PARAMETER_DESCRIPTORS, default, doc, type)


def _define_parameter(descriptors, default, doc, type):
    type = type or default.__class__
    # Create descriptor on-the-fly only for enum types.
    if type not in descriptors and issubclass(type, enum.Enum):
        descriptors[type] = SimpleParameterDescriptor(
            type=type,
            parse=type.__getitem__,
            show=lambda value: value.name,
            metavar='{%s}' % ','.join(m.name for m in type),
        )
    return Parameter(descriptors[type], default, doc)


class ParameterName(tuple):
    """Represent the fully-qualified name of a parameter."""

    def __str__(self):
        return '/'.join(self)

    def get_attr_name(self):
        """Get argparse.Namespace attribute name."""
        return '_'.join(name.replace('.', '_').lower() for name in self)

    def get_flag_str(self):
        """Get add_argument flag string."""
        return '--%s' % self.get_attr_name().replace('_', '-')

    def get_path_str(self):
        """Get a full path for indexing entries from config file."""
        return '.'.join(self)


def add_arguments_to(parser):
    """Add module-level namespaces to argparse.ArgumentParser."""
    return _add_arguments_to(_ROOT_NAMESPACE, parser)


def _add_arguments_to(root_namespace, parser):

    group = parser.add_argument_group(
        __name__,
        'module-level parameters',
    )
    group.add_argument(
        '--parameter-file',
        action='append',
        type=Path,
        metavar='PATH',
        help=(
            'read parameter values from JSON file(s)' if not yaml else
            'read parameter values from JSON or YAML file(s)'
        ),
    )

    parameter_list = []

    parameters = []
    sub_namespaces = []
    for name, parameter in root_namespace.items():
        if isinstance(parameter, Parameter):
            parameters.append((name, parameter))
        else:
            sub_namespaces.append((name, parameter))

    for name, parameter in parameters:
        parameter_name = ParameterName([name])
        parameter_list.append((parameter_name, parameter))
        parameter.descriptor.add_argument_to(
            parameter_name.get_flag_str(),
            parameter,
            parser,
        )

    # Add them alphabetically by name, which is stable regardless how
    # modules are imported.
    sub_namespaces.sort()
    parts = []
    for name, namespace in sub_namespaces:
        parts.append(name)
        _add_args_to(namespace, parts, parser, parameter_list)
        parts.pop()

    return parameter_list


def _add_args_to(namespace, parts, parser, parameter_list):
    """Add (sub-)namespaces to argparse.ArgumentParser."""

    parameters = []
    sub_namespaces = []
    for name, parameter in namespace.items():
        if isinstance(parameter, Parameter):
            parameters.append((name, parameter))
        else:
            sub_namespaces.append((name, parameter))

    if parameters:
        group = parser.add_argument_group('/'.join(parts), namespace.doc)
        for name, parameter in parameters:
            parts.append(name)
            parameter_name = ParameterName(parts)
            parts.pop()
            parameter_list.append((parameter_name, parameter))
            parameter.descriptor.add_argument_to(
                parameter_name.get_flag_str(),
                parameter,
                group,
            )

    for name, sub_namespace in sub_namespaces:
        parts.append(name)
        _add_args_to(sub_namespace, parts, parser, parameter_list)
        parts.pop()


def read_parameters_from(args, parameter_list):
    """Read parameter values from data sources."""

    if args.parameter_file:
        parameter_table = {
            parameter_name.get_path_str(): (parameter_name, parameter)
            for parameter_name, parameter in parameter_list
        }
        for path in args.parameter_file:
            _read_parameters(path, _load_file(path), [], parameter_table)

    for parameter_name, parameter in parameter_list:
        value = args.__dict__[parameter_name.get_attr_name()]
        if value is not None:
            LOG.debug('from command-line: %s = %r', parameter_name, value)
            parameter.set(value)


# NOTE: At the moment _read_parameters does not ignore undefined entries
# and will raise error upon seeing one.
def _read_parameters(path, parameter_values, parts, parameter_table):
    ASSERT(
        isinstance(parameter_values, dict),
        'expect parameter entry at namespace path: %s', parts,
    )
    for name, value in parameter_values.items():
        parts.append(name)
        entry = parameter_table.get(ParameterName(parts).get_path_str())
        if entry is None:
            _read_parameters(path, value, parts, parameter_table)
        else:
            parameter_name, parameter = entry
            LOG.debug('from file %s: %s = %r', path, parameter_name, value)
            parameter.set(value)
        parts.pop()


def _load_file(path):
    load_funcs = []
    if path.suffix == '.json':
        load_funcs.append(('JSON', json.loads))
    elif yaml and path.suffix in ('.yaml', '.yml'):
        load_funcs.append(('YAML', yaml.safe_load))
    else:
        # Unrecognizable suffix; let's try all formats.
        load_funcs.append(('JSON', json.loads))
        if yaml:
            load_funcs.append(('YAML', yaml.safe_load))
    content = path.read_text()
    for kind, load_func in load_funcs:
        try:
            return load_func(content)
        except Exception:
            LOG.debug(
                'does not look like a %s file: %s', kind, path,
                exc_info=True,
            )
    raise RuntimeError('cannot load parameters from file: %s' % path)
