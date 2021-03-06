#!/usr/bin/env python3

"""\
A foreman of a construction site is a (senior) worker who supervises and
directs other workers.  To build an application composed of multiple
sub-projects where each one has its own build tool and build process, we
borrow the notion of a "foreman" of a construction site to describe a
build tool that does not do any "real" build work, but instead invokes
the build tools of each sub-project, monitors their execution, and then
verifies their results.

There are two important design decisions:
  * The foreman only depends on Python 3.4 standard library.
  * The entirety of foreman is just one Python file.

In other words, you just copy `foreman.py` to anywhere you want, make
sure that Python 3.4 is installed, and you are good to go.  We need this
property because it is now common that a build process starts within a
vanilla operating system, usually inside a container, and the build tool
will have to bootstrap itself, like installing more build tools, before
it could actually start building something.  So reducing the install
steps of foreman down to minimum makes it very easy to be bootstrapped.

(We target Python 3.4 because that was when pathlib was added to the
standard library.)
"""

__all__ = [
    'ForemanError',
    'REMOVE',
    'get_relpath',
    'define_parameter',
    'define_rule',
    'rule',
    'to_path',
]

import argparse
import json
import logging
import sys
import types
from collections import ChainMap, OrderedDict, defaultdict
from functools import partial, total_ordering
from pathlib import Path, PurePath, PurePosixPath


LOG = logging.getLogger('foreman')
LOG.addHandler(logging.NullHandler())


BUILD_FILE = 'build.py'


# Sentinel value indicating that environment variables from parametric
# dependencies should be removed (but parameter values from command-line
# are not)
# TODO: Allow per-key removal
REMOVE = object()


### Core data model.


@total_ordering
class Label:
    """We use labels to name things.  A label is string starts with two
       slashes, followed by a path part and a name part that are joined
       by single colon; like: //some/path:and/some/name.
    """

    @classmethod
    def parse(cls, label_str, implicit_path=None):
        if label_str.startswith('//'):
            i = label_str.find(':')
            if i == -1:
                raise ValueError('lack name part in label: %r' % label_str)
            path = PurePosixPath(label_str[2:i])
            name = PurePosixPath(label_str[i+1:])
        else:
            if implicit_path is None:
                raise ValueError('lack path part in label: %r' % label_str)
            path = implicit_path
            if label_str.startswith(':'):
                name = PurePosixPath(label_str[1:])
            else:
                name = PurePosixPath(label_str)
        return cls(path, name)

    @classmethod
    def parse_name(cls, path, name_str):
        if name_str.startswith(':'):
            name_str = name_str[1:]
        return cls(path, PurePosixPath(name_str))

    def __init__(self, path, name):
        self.path = path
        self.name = name

    def __str__(self):
        return '//%s:%s' % (self.path, self.name)

    def __repr__(self):
        return 'Label<%s>' % str(self)

    def __hash__(self):
        return hash((self.path, self.name))

    def __eq__(self, other):
        return self.path == other.path and self.name == other.name

    def __lt__(self, other):
        return (self.path < other.path or
                (self.path == other.path and self.name < other.name))


class Things:
    """Colletion of things keyed by label.

       NOTE: When iterate over Things, it returns objects in the order
       when they are inserted instead of the order of label.  This
       provides some level of determinism of the ordering while still be
       as efficient as possible.
    """

    def __init__(self):
        self.things = OrderedDict()

    def __contains__(self, label):
        things = self.things.get(label.path)
        return things is not None and label.name in things

    def __getitem__(self, label):
        try:
            return self.things[label.path][label.name]
        except KeyError:
            raise KeyError(label) from None

    def __setitem__(self, label, thing):
        try:
            things = self.things[label.path]
        except KeyError:
            things = self.things[label.path] = OrderedDict()
        things[label.name] = thing

    def __iter__(self):
        for path, things in self.things.items():
            for name in things:
                yield Label(path, name)

    def get(self, label, default=None):
        try:
            return self[label]
        except KeyError:
            return default

    def values(self):
        for things in self.things.values():
            yield from things.values()

    def get_things(self, path):
        things = self.things.get(path)
        return list(things.values()) if things else []


class Parameter:

    def __init__(self, label):
        self.label = label
        self.doc = None
        self.default = None
        self.derive = None
        self.parse = None
        self.encode = None
        self.type = None

    def with_doc(self, doc):
        self.doc = doc
        return self

    def with_default(self, default):
        self.default = default
        return self

    def with_derive(self, derive):
        self.derive = derive
        return self

    def with_parse(self, parse):
        self.parse = parse
        return self

    def with_encode(self, encode):
        self.encode = encode
        return self

    def with_type(self, type):
        self.type = type
        return self

    def validate(self):
        """Validate parameter definition.

           You should call this right after its build file is executed.
        """
        if self.type is not None and self.default is not None:
            if not isinstance(self.default, self.type):
                raise ForemanError(
                    'default value of parameter %s is not %s-typed: %r' %
                    (self.label, self.type.__name__, self.default))
        if self.default is not None and self.derive is not None:
            raise ForemanError('default and derive are exclusive')

    def ensure_type(self, value):
        if self.type is not None and not isinstance(value, self.type):
            raise ForemanError('value of parameter %s is not %s-typed: %r' %
                               (self.label, self.type.__name__, value))
        return value


class Rule:

    class Dependency:

        def __init__(self, label, when, parameters):
            self.label = label
            self.when = when
            self.parameters = parameters

        def with_label(self, label):
            return Rule.Dependency(label, self.when, self.parameters)

    def __init__(self, label):
        self.label = label
        self.doc = None
        self.build = None
        self.dependencies = []
        self.from_reverse_dependencies = []
        self.reverse_dependencies = []
        self.annotations = {}

    def with_doc(self, doc):
        self.doc = doc
        return self

    def with_build(self, build):
        self.build = build
        return self

    def with_annotation(self, name, value):
        self.annotations[name] = value
        return self

    def without_annotation(self, name):
        self.annotations.pop(name, None)
        return self

    def depend(self, label, when=None, parameters=None):
        self.dependencies.append(Rule.Dependency(label, when, parameters))
        return self

    # Reverse dependency is usually for implementing "join point" kind
    # of build rules.  But note that even if you give foreman a join
    # point rule, it won't build all rules that reverse depend on this
    # join point, meaning that you still have to explicitly enumerate
    # them.  This is to prevent foreman from unintentionally building
    # too much stuff.  Also, for the same reason, if you give foreman a
    # rule that has reverse dependency, foreman will not build the rules
    # that are pointed by the reverse dependency unless you request it
    # explicitly.

    def reverse_depend(self, label, when=None, parameters=None):
        self.reverse_dependencies.append(
            Rule.Dependency(label, when, parameters))
        return self

    @property
    def all_dependencies(self):
        yield from self.dependencies
        yield from self.from_reverse_dependencies

    def parse_labels(self, implicit_path):
        """Parse label strings in the dependency definitions.

           You must call this right after its build file is executed.
        """
        for dep in self.dependencies:
            self._resolve_dep(dep, implicit_path)
        for dep in self.reverse_dependencies:
            self._resolve_dep(dep, implicit_path)

    @staticmethod
    def _resolve_dep(dep, implicit_path):
        if not isinstance(dep.label, Label):
            dep.label = Label.parse(dep.label, implicit_path)
        if dep.parameters and dep.parameters is not REMOVE:
            parameters = {}
            for label, value in dep.parameters.items():
                if not isinstance(label, Label):
                    label = Label.parse(label, implicit_path)
                parameters[label] = value
            dep.parameters = parameters


### Build file loader.


class Loader:

    def __init__(self, search_build_file):
        self.parameters = Things()
        self.rules = Things()
        self.path = None
        self.search_build_file = search_build_file

    def load_build_files(self, paths):
        """Load build files in breadth-first order."""
        return list(self._load_build_files(paths))

    def resolve_reverse_dependencies(self, rule_labels):
        """Add reverse dependencies from transitive closure of rules."""
        queue = []
        for label in rule_labels:
            if not isinstance(label, Label):
                label = Label.parse(label)
            queue.append(label)
        visited = set()
        while queue:
            label = queue.pop(0)
            if label in visited:
                continue
            rule = self.rules[label]
            for rdep in rule.reverse_dependencies:
                self.rules[rdep.label].from_reverse_dependencies.append(
                    rdep.with_label(rule.label))
            queue.extend(dep.label for dep in rule.dependencies)
            visited.add(label)

    def _load_build_files(self, paths):
        assert self.search_build_file is not None
        queue = list(paths)
        loaded_paths = set()
        while queue:
            # 1. Pop up the first label.
            label = queue.pop(0)
            if not isinstance(label, Label):
                label = Label.parse(label)
            # 2. Search and load the build file.
            if label.path not in loaded_paths:
                build_file_path = self.search_build_file(label.path)
                LOG.info('load build file %s', build_file_path)
                with Context(self, label.path):
                    self.load_build_file(label.path, build_file_path)
                loaded_paths.add(label.path)
            # 3. Notify caller.
            yield label
            # 4. Add not-loaded-yet rules to the queue.
            for rule in self.rules.get_things(label.path):
                for dep in rule.dependencies:
                    if dep.label not in self.rules:
                        queue.append(dep.label)
                # Also load build rules for reverse dependencies so that
                # when we later are resolving reverse dependencies, they
                # will be present.
                for dep in rule.reverse_dependencies:
                    if dep.label not in self.rules:
                        queue.append(dep.label)

        self._validate_rules()

    def _validate_rules(self):
        # Make sure that build rules do not refer to undefined parameters.
        for rule in self.rules.values():
            for dep in rule.all_dependencies:
                if dep.parameters and dep.parameters is not REMOVE:
                    for label in dep.parameters:
                        if label not in self.parameters:
                            msg = 'parameter %s is undefined' % label
                            raise ForemanError(msg)

    def load_build_file(self, label_path, build_file_path):
        """Load, compile, and execute one build file."""
        assert self.search_build_file is not None
        with build_file_path.open() as build_file_file:
            build_code = build_file_file.read()
        code = compile(build_code, str(build_file_path), 'exec')
        exec(code, {
            '__file__': str(build_file_path.absolute()),
            '__name__': str(label_path).replace('/', '.'),
        })
        # Validate parameters.
        for parameter in self.parameters.get_things(label_path):
            parameter.validate()
        # Parse the label of rule's dependencies.
        for rule in self.rules.get_things(label_path):
            rule.parse_labels(label_path)

    # Methods that are called from build files.

    def get_relpath(self):
        if self.path is None:
            raise RuntimeError('lack execution context')
        return self.path

    def parse_label_name(self, name):
        if self.path is None:
            raise RuntimeError('lack execution context')
        return Label.parse_name(self.path, name)

    def define_parameter(self, name):
        """Define a build parameter."""
        if self.path is None:
            raise RuntimeError('lack execution context')
        label = self.parse_label_name(name)
        if label in self.parameters:
            raise ForemanError('overwrite parameter %s' % label)
        LOG.debug('define parameter %s', label)
        parameter = self.parameters[label] = Parameter(label)
        return parameter

    def define_rule(self, name):
        """Define a build rule."""
        if self.path is None:
            raise RuntimeError('lack execution context')
        rule = Rule(self.parse_label_name(name))
        self.add_rule(rule)
        return rule

    def add_rule(self, rule):
        """Add a build rule object."""
        if rule.label in self.rules:
            raise ForemanError('overwrite rule %s' % rule.label)
        LOG.debug('define rule %s', rule.label)
        self.rules[rule.label] = rule

    def to_path(self, label):
        """Translate label to local path."""
        if self.path is None:
            raise RuntimeError('lack execution context')
        if isinstance(label, str):
            label = Label.parse(label, self.path)
        build_file_path = self.search_build_file(label.path)
        file_path = build_file_path.parent / label.name
        LOG.debug('resolve %s to: %s', label, file_path)
        return file_path


class Context:
    """Manage Loader.path."""

    def __init__(self, loader, path):
        self.loader = loader
        self._path = path

    def swap(self):
        self._path, self.loader.path = self.loader.path, self._path

    def __enter__(self):
        self.swap()

    def __exit__(self, *_):
        self.swap()


class Searcher:
    """Search build file."""

    def __init__(self, search_paths):
        assert search_paths
        self.search_paths = search_paths

    def __call__(self, path):
        for search_path in self.search_paths:
            build_file_path = search_path / path / BUILD_FILE
            if build_file_path.is_file():
                return build_file_path
        raise FileNotFoundError('No build file found for: %s' % path)


### Execution engine.


class Executor:

    def __init__(self, parameters, rules, loader, *, dry_run=False):
        self.parameters = parameters
        self.rules = rules
        self.loader = loader
        self.dry_run = dry_run
        self.build_ids = BuildIds()

    def execute(self, rule_label, environment):
        self.execute_rule(self.rules[rule_label], environment)

    def execute_rule(self, rule, environment):
        """Execute build rule in depth-first order."""

        if self.build_ids.check_and_add(rule, environment):
            return

        values = ParameterValues(
            self.parameters, environment, rule.label.path, self.loader)

        for dep in rule.all_dependencies:

            # Evaluate conditional dependency.
            if dep.when and not dep.when(values):
                continue

            if dep.parameters:
                if dep.parameters is REMOVE:
                    # The last map is the parameters from command-line
                    # and we should preserve it
                    next_env = ChainMap(environment.maps[-1])
                else:
                    next_env = environment.new_child()
                    next_env.update(dep.parameters)
            else:
                next_env = environment

            self.execute_rule(self.rules[dep.label], next_env)

        if LOG.isEnabledFor(logging.INFO):
            if environment.maps[0] is not environment.maps[-1]:
                current_env = environment.maps[0]
                LOG.info('execute rule %s with %s', rule.label, ', '.join(
                    '%s = %r' % (label, current_env[label])
                    for label in sorted(current_env)
                ))
            else:
                LOG.info('execute rule %s', rule.label)
        if not self.dry_run and rule.build:
            with Context(self.loader, rule.label.path):
                rule.build(values)


class BuildIds:
    """A build is uniquely identified by its rule and the environment
       when it is executed.
    """

    def __init__(self):
        self._values_lists = defaultdict(list)

    def check_and_add(self, rule, environment):
        """Check whether a build ID has been added and also add it at
           the same time.
        """
        # NOTE: Build ID is implemented in this indirect way because
        # values of an environment may be non-hashable.
        labels = tuple(sorted(environment))
        values_list = self._values_lists[rule.label, labels]
        values = [environment[label] for label in labels]
        if values in values_list:
            return True
        else:
            values_list.append(values)
            return False


class ParameterValues:
    """"A "view" of parameters and environment dict."""

    def __init__(self, parameters, environment, implicit_path, loader):
        self.parameters = parameters
        self.environment = environment
        self.implicit_path = implicit_path
        self.loader = loader

    def __contains__(self, label):
        return label in self.parameters

    def __getitem__(self, label):
        if isinstance(label, str):
            label = Label.parse(label, self.implicit_path)
        # Check if the parameter is defined first.
        parameter = self.parameters[label]
        if label in self.environment:
            return parameter.ensure_type(self.environment[label])
        elif parameter.derive:
            with Context(self.loader, parameter.label.path):
                # Create a ParameterValues with different implicit_path.
                value = parameter.derive(ParameterValues(
                    self.parameters,
                    self.environment,
                    parameter.label.path,
                    self.loader,
                ))
            return parameter.ensure_type(value)
        else:
            return parameter.default


### APIs for build files.


class ForemanError(Exception):
    """Base error class of foreman."""
    pass


#
# LOADER is the only global variable, which is used in both:
#   * build file loading phase
#   * build rule executing phase
# And it serves as a context in both phases (it's not simply a loader
# anymore).
#
LOADER = None


def get_relpath():
    """Return relative path of the current build file."""
    return LOADER.get_relpath()


def define_parameter(name):
    return LOADER.define_parameter(name)


define_parameter.bool_typed = lambda name: (
    define_parameter(name)
    .with_type(bool)
    .with_parse(lambda value: {'true': True, 'false': False}[value.lower()]))


define_parameter.int_typed = lambda name: (
    define_parameter(name)
    .with_type(int))


define_parameter.list_typed = lambda name: (
    define_parameter(name)
    .with_type(list)
    .with_parse(lambda value: value.split(',')))


define_parameter.path_list_typed = lambda name: (
    define_parameter(name)
    .with_type(list)
    .with_parse(lambda value: list(map(Path, value.split(',')))))


define_parameter.namedtuple_typed = lambda namedtuple, name: (
    define_parameter(name)
    .with_type(namedtuple)
    .with_parse(lambda value: namedtuple(*value.split(','))))


define_parameter.path_typed = lambda name: (
    define_parameter(name)
    .with_type(Path))


def define_rule(name):
    return LOADER.define_rule(name)


def _decorate_rule(func_or_rule, *,
                   # "Private" arguments
                   _define=False,
                   _name=None,
                   _annotation=None,
                   _depend=None,
                   _reverse_depend=None):
    if isinstance(func_or_rule, Rule):
        rule = func_or_rule
        if _name:
            rule.label = LOADER.parse_label_name(_name)
    else:
        rule = (Rule(LOADER.parse_label_name(_name or func_or_rule.__name__))
                .with_doc(func_or_rule.__doc__)
                .with_build(func_or_rule))
    if _annotation:
        rule.with_annotation(*_annotation)
    if _depend:
        rule.dependencies.insert(0, _depend)
    if _reverse_depend:
        rule.reverse_dependencies.insert(0, _reverse_depend)
    if _define:
        LOADER.add_rule(rule)
    return rule


def rule(arg):
    """Decorator-chain style for creating build rules.

       This is for creating build rule, and it does not represent build
       rules (you are looking for the Rule class above).

       You may define build rules in ways like:

           @rule
           def simple_rule(_):
               pass

           @rule('complex/rule/name')
           @rule.depend('simeple_rule')
           def build(_):
               pass
    """
    # arg's type is either str, func, or Rule
    if isinstance(arg, str):
        return partial(_decorate_rule, _name=arg, _define=True)
    else:
        return _decorate_rule(arg, _define=True)


rule.annotate = lambda name, value: partial(
    _decorate_rule,
    _annotation=(name, value),
)


rule.depend = lambda label, when=None, parameters=None: partial(
    _decorate_rule,
    _depend=Rule.Dependency(label, when=when, parameters=parameters),
)


rule.reverse_depend = lambda label, when=None, parameters=None: partial(
    _decorate_rule,
    _reverse_depend=Rule.Dependency(label, when=when, parameters=parameters),
)


def to_path(label):
    return LOADER.to_path(label)


### Command-line entries.


def main(argv):
    parser = argparse.ArgumentParser(
        description="""A build tool that supervises build tools.""")

    def add_common_args(parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            '--debug', action='store_true',
            help="""enable debug output""")
        group.add_argument(
            '--quiet', action='store_true',
            help="""disable output""")
        parser.add_argument(
            '--path', action='append',
            help="""add path to search for build files (default to the
                    current directory if none is provided)""")

    subparsers = parser.add_subparsers(help="""Sub-commands.""")
    # http://bugs.python.org/issue9253
    subparsers.dest = 'command'
    subparsers.required = True

    parser_build = subparsers.add_parser(
        'build', help="""Start and supervise a build.""")
    add_common_args(parser_build)
    parser_build.add_argument(
        '--dry-run', action='store_true',
        help="""do not really execute builds""")
    parser_build.add_argument(
        '--parameter', action='append',
        help="""set build parameter; the format is either label=value or
                @file.json""")
    parser_build.add_argument(
        'rule', nargs='+', help="""add rule to build""")
    parser_build.set_defaults(command=command_build)

    parser_list = subparsers.add_parser(
        'list', help="""List build rules and parameters.""")
    add_common_args(parser_list)
    parser_list.add_argument(
        'rule', nargs='+', help="""add build rule to list from""")
    parser_list.set_defaults(command=command_list)

    args = parser.parse_args(argv[1:])

    if args.debug:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.WARNING
    else:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )

    # Hack to let build files do `import foreman`.
    if 'foreman' not in sys.modules:
        sys.modules['foreman'] = sys.modules['__main__']

    if args.path:
        search_paths = []
        for search_path in args.path:
            search_path = Path(search_path)
            if not search_path.is_dir():
                LOG.debug('ignore non-directory search path: %s', search_path)
                continue
            search_path = search_path.resolve()
            if search_path in search_paths:
                LOG.debug('ignore duplicated search path: %s', search_path)
                continue
            LOG.debug('add search path: %s', search_path)
            search_paths.append(search_path)
        # Latter --path overrides former (like --parameter).
        search_paths.reverse()
    else:
        search_paths = [Path.cwd()]
    searcher = Searcher(search_paths)

    global LOADER
    LOADER = Loader(searcher)

    return args.command(args, LOADER)


def command_build(args, loader):

    rule_labels = []
    for rule_label in args.rule:
        rule_label = Label.parse(rule_label)
        if rule_label not in rule_labels:
            rule_labels.append(rule_label)

    loader.load_build_files(rule_labels)
    loader.resolve_reverse_dependencies(rule_labels)

    executor = Executor(
        loader.parameters, loader.rules,
        loader,
        dry_run=args.dry_run,
    )

    environment = ChainMap()
    for spec in args.parameter or ():
        if spec.startswith('@'):
            with open(spec[1:], 'r') as input_file:
                pv_pairs = json.loads(input_file.read()).items()
        else:
            pv_pairs = [spec.split('=', maxsplit=1)]
        for parameter_label, value in pv_pairs:
            parameter_label = Label.parse(parameter_label)
            try:
                parameter = executor.parameters[parameter_label]
            except KeyError:
                msg = 'parameter %s is undefined' % parameter_label
                raise ForemanError(msg) from None
            if value is None:
                pass
            elif parameter.parse:
                value = parameter.parse(value)
            elif parameter.type:
                value = parameter.type(value)
            environment[parameter.label] = value
            LOG.debug('parameter %s is set to: %r', parameter.label, value)

    # NOTE: It might not be clear but the semantics we implement here is
    # similar to `make`.  The executor records the rules that have been
    # executed and do not execute them twice.  And so no matter what
    # order of rules you type on the command-line, it is always the same
    # transitive closure of rules that will be executed (but the order
    # of execution may be different).
    for rule_label in rule_labels:
        executor.execute(rule_label, environment)

    return 0


def command_list(args, loader):

    def format_parameter(parameter):
        contents = OrderedDict()
        contents['label'] = str(parameter.label)
        contents['doc'] = parameter.doc
        if parameter.derive is not None:
            with Context(loader, parameter.label.path):
                contents['default'] = parameter.derive(
                    ParameterValues(
                        loader.parameters, {}, parameter.label.path, loader))
        elif parameter.default is not None:
            contents['default'] = parameter.default
        if parameter.encode and 'default' in contents:
            contents['default'] = parameter.encode(contents['default'])
        contents['custom_parser'] = bool(parameter.parse)
        contents['custom_encoder'] = bool(parameter.encode)
        contents['derived'] = bool(parameter.derive)
        if parameter.type is not None:
            contents['type'] = parameter.type.__name__
        return contents

    def format_rule(rule):
        return OrderedDict([
            ('label', str(rule.label)),
            ('doc', rule.doc),
            ('annotations', OrderedDict([
                (name, rule.annotations[name])
                for name in sorted(rule.annotations)
            ])),
            ('dependencies',
             list(map(format_dependency, rule.dependencies))),
            ('reverse_dependencies',
             list(map(format_dependency, rule.reverse_dependencies))),
            ('all_dependencies',
             list(map(format_dependency, rule.all_dependencies))),
        ])

    def format_dependency(dependency):
        contents = OrderedDict()
        contents['label'] = str(dependency.label)
        contents['conditional'] = bool(dependency.when)
        if dependency.parameters:
            if dependency.parameters is REMOVE:
                contents['parameters'] = 'REMOVE'
            else:
                contents['parameters'] = OrderedDict([
                    (str(label), dependency.parameters[label])
                    for label in sorted(dependency.parameters)
                ])
        return contents

    # Provide encoders for some common types.
    def encode_object(obj):
        if isinstance(obj, PurePath):
            return str(obj)
        elif isinstance(obj, types.FunctionType):
            return '<function %s#%s>' % (obj.__module__, obj.__qualname__)
        else:
            raise TypeError(repr(obj) + ' is not JSON serializable')

    build_file_contents = OrderedDict()
    labels = loader.load_build_files(args.rule)
    loader.resolve_reverse_dependencies(args.rule)
    for label in labels:
        path_str = '//%s' % label.path
        if path_str in build_file_contents:
            continue
        build_file_contents[path_str] = OrderedDict([
            ('parameters',
             list(map(format_parameter,
                      loader.parameters.get_things(label.path)))),
            ('rules',
             list(map(format_rule,
                      loader.rules.get_things(label.path)))),
        ])

    print(json.dumps(
        build_file_contents,
        indent=4,
        default=encode_object,
    ))

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
