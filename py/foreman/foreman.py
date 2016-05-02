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
    'define_parameter',
    'define_rule',
    'decorate_rule',
]

import argparse
import json
import logging
import sys
from collections import ChainMap, OrderedDict, defaultdict
from pathlib import Path, PurePosixPath


LOG = logging.getLogger('foreman')
LOG.addHandler(logging.NullHandler())


BUILD_FILE = 'build.py'


### Core data model.


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


class Things:
    """Colletion of things keyed by label."""

    def __init__(self):
        self.things = {}

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
        for things in self.things.values():
            yield from things

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
        self.parse = None
        self.type = None

    def with_doc(self, doc):
        self.doc = doc
        return self

    def with_default(self, default):
        self.default = default
        return self

    def with_parse(self, parse):
        self.parse = parse
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


class Rule:

    class Dependency:

        def __init__(self, label, when, configs):
            self.label = label
            self.when = when
            self.configs = configs

    def __init__(self, label):
        self.label = label
        self.doc = None
        self.build = None
        self.dependencies = []
        self.implicit_dependencies = []

    def with_doc(self, doc):
        self.doc = doc
        return self

    def with_build(self, build):
        self.build = build
        return self

    def depend(self, label, when=None, configs=None):
        self.dependencies.append(Rule.Dependency(label, when, configs))
        return self

    @property
    def all_dependencies(self):
        yield from self.dependencies
        yield from self.implicit_dependencies

    def parse_labels(self, implicit_path):
        """Parse label strings in the dependency definitions.

           You must call this right after its build file is executed.
        """
        for dep in self.dependencies:
            if not isinstance(dep.label, Label):
                dep.label = Label.parse(dep.label, implicit_path)
            if dep.configs:
                configs = []
                for label, value in dep.configs:
                    if not isinstance(label, Label):
                        label = Label.parse(label, implicit_path)
                    configs.append((label, value))
                dep.configs = configs


### Execution engine.


PARAMETERS = Things()
RULES = Things()


CURRENT_PATH = None


class Context:
    """Manage global state `CURRENT_PATH`."""

    def __init__(self, path):
        self.path = path
        self.previous_path = None

    def __enter__(self):
        global CURRENT_PATH
        self.previous_path, CURRENT_PATH = CURRENT_PATH, self.path

    def __exit__(self, *_):
        global CURRENT_PATH
        CURRENT_PATH = self.previous_path


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


def load_build_files(paths, search_build_file):
    """Load build files in breadth-first order."""
    queue = list(paths)
    loaded_paths = set()
    while queue:
        # 1. Pop up the first label.
        label = queue.pop(0)
        if not isinstance(label, Label):
            label = Label.parse(label)
        # 2. Search and load the build file.
        if label.path not in loaded_paths:
            build_file_path = search_build_file(label.path)
            LOG.info('load build file %s', build_file_path)
            with Context(label.path):
                load_build_file(label.path, build_file_path, search_build_file)
            loaded_paths.add(label.path)
        # 3. Notify caller.
        yield label
        # 4. Add not-created-yet rules to the queue.
        for dep in RULES[label].all_dependencies:
            if dep.label not in RULES:
                queue.append(dep.label)
    # Make sure that build rules do not refer to undefined parameters.
    for rule in RULES.values():
        for dep in rule.all_dependencies:
            if dep.configs:
                for label, _ in dep.configs:
                    if label not in PARAMETERS:
                        raise ForemanError('parameter %s is undefined' % label)


def load_build_file(label_path, build_file_path, search_build_file):
    """Load, compile, and execute one build file."""
    # Path.read_text() is added until Python 3.5 :(
    with build_file_path.open() as build_file:
        code = build_file.read()
    code = compile(code, str(build_file_path), 'exec')
    exec(code, {'__name__': str(label_path).replace('/', '.')})
    # Validate parameters.
    for parameter in PARAMETERS.get_things(label_path):
        parameter.validate()
    # Parse the label of rule's dependencies.
    for rule in RULES.get_things(label_path):
        rule.parse_labels(label_path)
    # Compute rules' implicit dependencies.
    for rule in RULES.get_things(label_path):
        for path in list(rule.label.path.parents)[:-1]:
            try:
                search_build_file(path)
            except FileNotFoundError:
                pass
            else:
                rule.implicit_dependencies.append(Rule.Dependency(
                    Label.parse_name(path, path.name),
                    None,
                    None,
                ))


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

    def __init__(self, parameters, environment, implicit_path):
        self.parameters = parameters
        self.environment = environment
        self.implicit_path = implicit_path

    def __contains__(self, label):
        return label in self.parameters

    def __getitem__(self, label):
        if isinstance(label, str):
            label = Label.parse(label, self.implicit_path)
        try:
            return self.environment[label]
        except KeyError:
            parameter = self.parameters.get(label)
            if parameter is None:
                raise
            return parameter.default


def execute_rule(rule, environment, build_ids):
    """Execute build rule in depth-first order."""

    if build_ids.check_and_add(rule, environment):
        return

    values = ParameterValues(PARAMETERS, environment, rule.label.path)

    for dep in rule.all_dependencies:

        # Evaluate conditional dependency.
        if dep.when and not dep.when(values):
            continue

        if dep.configs:
            next_env = environment.new_child()
            next_env.update(dep.configs)
        else:
            next_env = environment

        execute_rule(RULES[dep.label], next_env, build_ids)

    if LOG.isEnabledFor(logging.INFO):
        if environment.maps[0] is not environment.maps[-1]:
            current_env = environment.maps[0]
            LOG.info('execute rule %s with %s', rule.label, ', '.join(
                '%s = %r' % (label, current_env[label])
                for label in sorted(current_env)
            ))
        else:
            LOG.info('execute rule %s', rule.label)
    if rule.build:
        rule.build(values)


### Implementation of public API.


class ForemanError(Exception):
    """Base error class of foreman."""
    pass


def define_parameter(name):
    """Define a build parameter."""
    if CURRENT_PATH is None:
        raise RuntimeError('lack execution context')
    label = Label.parse_name(CURRENT_PATH, name)
    if label in PARAMETERS:
        raise ForemanError('overwrite parameter %s' % label)
    LOG.debug('define parameter %s', label)
    parameter = PARAMETERS[label] = Parameter(label)
    return parameter


def define_rule(name):
    """Define a build rule."""
    if CURRENT_PATH is None:
        raise RuntimeError('lack execution context')
    label = Label.parse_name(CURRENT_PATH, name)
    if label in RULES:
        raise ForemanError('overwrite rule %s' % label)
    LOG.debug('define rule %s', label)
    rule = RULES[label] = Rule(label)
    return rule


def decorate_rule(*args):
    """Helper for creating simple build rule."""
    if len(args) == 1 and not isinstance(args[0], str):
        build = args[0]
        return (
            define_rule(build.__name__)
            .with_doc(build.__doc__)
            .with_build(build)
        )
    else:
        def wrapper(build):
            rule = decorate_rule(build)
            for dep in args:
                rule.depend(dep)
            return rule
        return wrapper


### Command-line entries.


def main(argv):
    parser = argparse.ArgumentParser(
        description="""A build tool that supervises build tools.""")
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

    subparsers = parser.add_subparsers(
        help="""Sub-commands.""")

    parser_build = subparsers.add_parser(
        'build', help="""Start and supervise a build.""")
    parser_build.add_argument(
        '--parameter', action='append', default=(),
        help="""set build parameter; the format is either label=value or
                @file.json""")
    parser_build.add_argument(
        'rule', nargs='+', help="""add rule to build""")
    parser_build.set_defaults(command=command_build)

    parser_list = subparsers.add_parser(
        'list', help="""List build rules and parameters.""")
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
    else:
        search_paths = [Path.cwd()]
    searcher = Searcher(search_paths)

    return args.command(args, searcher)


def command_build(args, search_build_file):

    rule_labels = []
    for rule_label in args.rule:
        rule_label = Label.parse(rule_label)
        if rule_label not in rule_labels:
            rule_labels.append(rule_label)

    for _ in load_build_files(rule_labels, search_build_file):
        pass

    environment = ChainMap()
    for spec in args.parameter:
        if spec.startswith('@'):
            with open(spec[1:], 'r') as input_file:
                pv_pairs = json.loads(input_file.read())
        else:
            pv_pairs = [spec.split('=', maxsplit=1)]
        for parameter_label, value in pv_pairs:
            parameter_label = Label.parse(parameter_label)
            try:
                parameter = PARAMETERS[parameter_label]
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

    for rule_label in rule_labels:
        execute_rule(RULES[rule_label], environment, BuildIds())

    return 0


def command_list(args, search_build_file):

    def format_parameter(parameter):
        contents = OrderedDict()
        contents['label'] = str(parameter.label)
        contents['doc'] = parameter.doc
        if parameter.default is not None:
            contents['default'] = parameter.default
        contents['custom_parser'] = bool(parameter.parse)
        if parameter.type is not None:
            contents['type'] = parameter.type.__name__
        return contents

    def format_rule(rule):
        return OrderedDict([
            ('label', str(rule.label)),
            ('doc', rule.doc),
            ('dependencies',
             list(map(format_dependency, rule.dependencies))),
            ('implicit_dependencies',
             list(map(format_dependency, rule.implicit_dependencies))),
        ])

    def format_dependency(dependency):
        contents = OrderedDict()
        contents['label'] = str(dependency.label)
        contents['conditional'] = bool(dependency.when)
        if dependency.configs:
            contents['configs'] = OrderedDict([
                (str(label), value)
                for label, value in dependency.configs
            ])
        return contents

    build_file_contents = OrderedDict()
    for label in load_build_files(args.rule, search_build_file):
        path_str = '//%s' % label.path
        if path_str in build_file_contents:
            continue
        build_file_contents[path_str] = OrderedDict([
            ('parameters',
             list(map(format_parameter, PARAMETERS.get_things(label.path)))),
            ('rules',
             list(map(format_rule, RULES.get_things(label.path)))),
        ])
    print(json.dumps(build_file_contents, indent=4))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
