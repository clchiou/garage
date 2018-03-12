"""Parameters.

The use case of the `parameters` module is for module-level, (mostly)
read-only parameters.  The parameter values are read from two sources,
higher precedence one comes first:
  * Command-line arguments.
  * Configuration files.

Parameters are grouped by a (hierarchy of) namespaces.

For now, parameters have a few deliberately-made design constraints:
  * It only supports scalar, vector, and matrix parameter value types,
    and does not provide interface for adding custom parameter types.
    * Scalar types are: bool, dict, int, float, str, Enum, and Path.
      * We treat dict as a black box without imposing constraints on its
        keys or values; thus it makes sense to declare dict as a scalar
        type in this context.
    * Vector is typing.Tuple[scalar_types].
    * Matrix is typing.List[scalar or typing.Tuple[scalar_types]].
  * It does not read parameter values from the environment because:
    * Environment variables are not explicit, and we might unwittingly
      override a parameter.
    * It looks like command-ling arguments and configuration files may
      cover all use cases.
We might loose these constraints later after we try more use cases.
"""

__all__ = [
    'create',
    'create_namespace',
    'define_namespace',
]

import collections
import enum
import json
import logging
import typing
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
        self.parameters = collections.OrderedDict()

    def __bool__(self):
        return bool(self.parameters)

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

    @property
    def action(self):
        """Return action for ArgumentParser.add_argument."""
        raise NotImplementedError

    @property
    def nargs(self):
        """Return nargs for ArgumentParser.add_argument."""
        raise NotImplementedError

    @property
    def metavar(self):
        """Return metavar for ArgumentParser.add_argument."""
        raise NotImplementedError

    def show(self, value):
        """Stringify value for display purpose (not intended to be
        parsed later).
        """
        raise NotImplementedError

    def parse(self, arg_value):
        """Parse parameter value from ArgumentParser result, and raise
        when arg_value is ill-formed.
        """
        raise NotImplementedError

    def translate(self, value):
        """Translate a value (from JSON or YAML parser) to a suitable
        parameter value, and raise when value is incomprehensible.
        """
        raise NotImplementedError

    def validate(self, value):
        """Raise on invalid parameter value."""
        raise NotImplementedError

    def format_help(self, parameter):
        if parameter.unit:
            default = 'default: %s %s' % (
                self.show(parameter.default), parameter.unit)
        else:
            default = 'default: %s' % self.show(parameter.default)
        doc = parameter.doc
        if doc is None:
            doc = default
        else:
            doc = '%s (%s)' % (doc, default)
        return doc

    def add_argument_to(self, flag, parameter, parser):
        #
        # Do not it call with `type=self.parse` because when nargs > 1,
        # ArgumentParser applies `type` on each argument values rather
        # than applying `type` on them as a single tuple.
        #
        # Do not provide parameter.default to parser.add_argument as we
        # check `args.var_name is None` at later point to know whether
        # a parameter is overridden from command-line.
        #
        parser.add_argument(
            flag,
            action=self.action,
            nargs=self.nargs,
            metavar=self.metavar,
            help=self.format_help(parameter),
        )


class ScalarParameterDescriptor(ParameterDescriptor):

    def __init__(
            self, type, *,
            parse=None, translate=None, show=str, metavar=None):
        self._type = type
        self._parse = parse or type
        self._translate = translate
        self._show = show
        self._metavar = metavar or self._type.__name__.upper()

    @property
    def action(self):
        return 'store'

    @property
    def nargs(self):
        return None

    @property
    def metavar(self):
        return self._metavar

    def show(self, value):
        return self._show(value)

    def parse(self, arg_value):
        return self._parse(arg_value)

    def translate(self, value):
        if self._translate:
            value = self._translate(value)
        return value

    def validate(self, value):
        ASSERT.type_of(value, self._type)


class VectorParameterDescriptor(ParameterDescriptor):

    def __init__(self, cell_descriptors):
        self._cell_descriptors = cell_descriptors

    def _assert_dimension(self, vector):
        ASSERT(
            len(self._cell_descriptors) == len(vector),
            'expect %d-dimension vector: %r',
            len(self._cell_descriptors), vector,
        )

    @property
    def action(self):
        return 'store'

    @property
    def nargs(self):
        return len(self._cell_descriptors)

    @property
    def metavar(self):
        return tuple(
            descriptor.metavar for descriptor in self._cell_descriptors)

    def show(self, value):
        self._assert_dimension(value)
        return '(%s)' % ', '.join(
            descriptor.show(cell)
            for descriptor, cell in zip(self._cell_descriptors, value)
        )

    def parse(self, arg_value):
        self._assert_dimension(arg_value)
        return tuple(
            descriptor.parse(cell)
            for descriptor, cell in zip(self._cell_descriptors, arg_value)
        )

    def translate(self, value):
        self._assert_dimension(value)
        return tuple(
            descriptor.translate(cell)
            for descriptor, cell in zip(self._cell_descriptors, value)
        )

    def validate(self, value):
        self._assert_dimension(value)
        for descriptor, cell in zip(self._cell_descriptors, value):
            descriptor.validate(cell)


class MatrixParameterDescriptor(ParameterDescriptor):

    def __init__(self, vector_descriptor):
        self._vector_descriptor = vector_descriptor

    @property
    def action(self):
        return 'append'

    @property
    def nargs(self):
        return self._vector_descriptor.nargs

    @property
    def metavar(self):
        return self._vector_descriptor.metavar

    def show(self, value):
        return '[%s]' % ', '.join(map(self._vector_descriptor.show, value))

    def parse(self, arg_value):
        return list(map(self._vector_descriptor.parse, arg_value))

    def translate(self, value):
        return list(map(self._vector_descriptor.translate, value))

    def validate(self, value):
        for vector in value:
            self._vector_descriptor.validate(vector)


class OneDimensionalMatrixParameterDescriptor(ParameterDescriptor):

    def __init__(self, cell_descriptor):
        self._cell_descriptor = cell_descriptor

    @property
    def action(self):
        return 'append'

    @property
    def nargs(self):
        return None

    @property
    def metavar(self):
        return self._cell_descriptor.metavar

    def show(self, value):
        return '[%s]' % ', '.join(map(self._cell_descriptor.show, value))

    def parse(self, arg_value):
        return list(map(self._cell_descriptor.parse, arg_value))

    def translate(self, value):
        return list(map(self._cell_descriptor.translate, value))

    def validate(self, value):
        for cell in value:
            self._cell_descriptor.validate(cell)


class Parameter:
    """Represent a parameter.

    The current design requires that a parameter always has a default
    value, with the assumption that most of the time, the majority of
    parameter values will not be overridden, and thus they are required
    to have a default value.
    """

    def __init__(self, descriptor, default, unit, doc):
        descriptor.validate(default)
        self.default = default
        self.unit = unit
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


def define_namespace(module_name, doc=None, *, namespace=None):
    """Define (module-level) parameter namespace."""
    return _define_namespace(_ROOT_NAMESPACE, module_name, doc, namespace)


def _define_namespace(root_namespace, module_name, doc, namespace):

    # Make special case for __main__.
    if module_name == '__main__':
        if namespace is not None:
            nspace = ASSERT.type_of(namespace, Namespace)._namespace
            ASSERT(
                not (set(root_namespace) & set(nspace)),
                'expect not overriding module-level namespace: %r vs %r',
                root_namespace.parameters, nspace.parameters,
            )
            root_namespace.parameters.update(nspace.parameters)
        return Namespace(root_namespace)

    ASSERT(
        module_name not in root_namespace,
        'expect not redefining namespace: %s', module_name,
    )
    if namespace is None:
        root_namespace[module_name] = nspace = ParameterNamespace(doc)
        return Namespace(nspace)
    else:
        ASSERT.type_of(namespace, Namespace)
        root_namespace[module_name] = namespace._namespace
        return namespace


_SCALAR_PARAMETER_DESCRIPTORS = {
    bool: ScalarParameterDescriptor(
        type=bool,
        parse=lambda v: ASSERT.in_(v, ('true', 'false')) == 'true',
        show=lambda value: 'true' if value else 'false',
        metavar='{true,false}',
    ),
    float: ScalarParameterDescriptor(float),
    int: ScalarParameterDescriptor(int),
    str: ScalarParameterDescriptor(str, show=repr),
    Path: ScalarParameterDescriptor(Path),
    # Make an exception for dict-like types.
    collections.Mapping: ScalarParameterDescriptor(
        type=collections.Mapping,
        parse=json.loads,
        show=json.dumps,
        metavar='JSON_STR',
    ),
}


_VECTOR_PARAMETER_DESCRIPTORS = {}


_MATRIX_PARAMETER_DESCRIPTORS = {}


def create_namespace(doc=None):
    """Create a parameter (sub-)namespace."""
    return Namespace(ParameterNamespace(doc))


def create(default, doc=None, type=None, unit=None):
    """Create a parameter.

    The parameter type is inferred from the default value unless
    overridden.
    """
    return _create_parameter(
        _MATRIX_PARAMETER_DESCRIPTORS,
        _VECTOR_PARAMETER_DESCRIPTORS,
        _SCALAR_PARAMETER_DESCRIPTORS,
        default, doc, type, unit
    )


def _create_parameter(
        matrix_descriptors,
        vector_descriptors,
        scalar_descriptors,
        default, doc, type, unit):

    type = type or default.__class__

    if issubclass(type, list):
        if not isinstance(type, typing.GenericMeta):
            type = infer_matrix_type(default)
        descriptor = define_matrix_descriptor(
            matrix_descriptors,
            vector_descriptors,
            scalar_descriptors,
            type,
        )

    elif issubclass(type, tuple):
        if not isinstance(type, typing.GenericMeta):
            type = infer_vector_type(default)
        descriptor = define_vector_descriptor(
            vector_descriptors,
            scalar_descriptors,
            type,
        )

    elif is_scalar_type(type):
        descriptor = define_scalar_descriptor(
            scalar_descriptors,
            type,
        )

    else:
        ASSERT.fail('expect scalar, vector, or matrix: %r %r', type, default)

    return Parameter(descriptor, default, unit, doc)


def define_scalar_descriptor(
        scalar_descriptors,
        type):
    # Create scalar descriptor on-the-fly for enum types.
    if type not in scalar_descriptors and issubclass(type, enum.Enum):
        scalar_descriptors[type] = ScalarParameterDescriptor(
            type=type,
            parse=type.__getitem__,
            translate=type.__getitem__,
            show=lambda value: value.name,
            metavar='{%s}' % ','.join(m.name for m in type),
        )
    # pathlib returns platform-dependent subclass of Path.
    if issubclass(type, Path):
        type = Path
    elif issubclass(type, collections.Mapping):
        type = collections.Mapping
    return scalar_descriptors[type]


def define_vector_descriptor(
        vector_descriptors,
        scalar_descriptors,
        type):
    descriptor = vector_descriptors.get(type)
    if descriptor is None:
        cds = tuple(
            define_scalar_descriptor(
                scalar_descriptors,
                cell_type,
            )
            for cell_type in type.__args__
        )
        descriptor = vector_descriptors[type] = VectorParameterDescriptor(cds)
    return descriptor


def define_matrix_descriptor(
        matrix_descriptors,
        vector_descriptors,
        scalar_descriptors,
        type):
    descriptor = matrix_descriptors.get(type)
    if descriptor is None:
        vector_type = type.__args__[0]
        if not issubclass(vector_type, typing.Tuple):
            descriptor = OneDimensionalMatrixParameterDescriptor(
                define_scalar_descriptor(
                    scalar_descriptors,
                    vector_type,
                ),
            )
        elif len(vector_type.__args__) == 1:
            descriptor = OneDimensionalMatrixParameterDescriptor(
                define_scalar_descriptor(
                    scalar_descriptors,
                    vector_type.__args__[0],
                ),
            )
        else:
            descriptor = MatrixParameterDescriptor(
                define_vector_descriptor(
                    vector_descriptors,
                    scalar_descriptors,
                    vector_type,
                ),
            )
        matrix_descriptors[type] = descriptor
    return descriptor


_SCALAR_TYPES = (bool, float, int, str, Path, enum.Enum, collections.Mapping)


def is_scalar_type(type):
    return issubclass(type, _SCALAR_TYPES)


def infer_vector_type(value):
    """Infer vector type from value.

    For example, (1, 'hello') will be typing.Tuple[int, str].
    """
    ASSERT.type_of(value, tuple)
    ASSERT(value, 'expect non-empty value for inferring: %r', value)
    type = typing.Tuple[tuple(cell.__class__ for cell in value)]
    ASSERT(
        all(map(is_scalar_type, type.__args__)),
        'expect a vector-typed value: %r', value,
    )
    return type


def infer_matrix_type(value):
    """Infer matrix type from value.

    For example, [('x', 1)] will be typing.List[typing.Tuple[str, int]].

    For developer ergonomics, one-dimensional matrix can be represented
    by [1, 2, 3], which will be typing.List[typing.Tuple[int]].
    """
    ASSERT.type_of(value, list)
    ASSERT(value, 'expect non-empty value for inferring: %r', value)
    if is_scalar_type(value[0].__class__):
        # Special case for one-dimensional matrix.
        ASSERT(
            all(isinstance(cell, value[0].__class__) for cell in value[1:]),
            'expect same cell type for a matrix: %r', value
        )
        row_type = typing.Tuple[value[0].__class__]
    else:
        row_type = infer_vector_type(value[0])
        ASSERT(
            all(infer_vector_type(row) is row_type for row in value[1:]),
            'expect same cell type for a matrix: %r', value
        )
    return typing.List[row_type]


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

    if not root_namespace:
        return []

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

    if not parameter_list:
        return

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
            value = parameter.descriptor.parse(value)
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
            value = parameter.descriptor.translate(value)
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
