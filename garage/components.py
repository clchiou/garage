"""Initialize modules with 1- or 2- stages of startup.

The first startup is the normal, global startup object.  It is called
before main(), which will parse command-line arguments and it will
resolve MAIN and ARGS.  Its dependency graph is:

  PARSER ---> PARSE --+--> ARGS
                      |
              ARGV ---+

  MAIN

The second startup is component_startup.  You may use the second stage
startup to initialize "heavy" objects such as database connection.
"""

__all__ = [
    'ARGS',
    'EXIT_STACK',
    'MAIN',
    'PARSE',
    'PARSER',

    'Component',
    'make_require',
    'make_provide',
    'make_full_name',

    'bind',
    'vars_as_namespace',
    'main',
    'parse_argv',
]

import functools
import types
from collections import namedtuple

from startup import startup as startup_

from garage import asserts
from garage.collections import DictAsAttrs


def _is_full_name(name):
    return ':' in name


def make_full_name(module_name, name):
    return '%s:%s' % (module_name, name)


def _get_name(maybe_full_name):
    return maybe_full_name[maybe_full_name.rfind(':')+1:]


ARGS = make_full_name(__name__, 'args')
ARGV = make_full_name(__name__, 'argv')
EXIT_STACK = make_full_name(__name__, 'exit_stack')
MAIN = make_full_name(__name__, 'main')
PARSE = make_full_name(__name__, 'parse')
PARSER = make_full_name(__name__, 'parser')


def _make_full_names(module_name, maybe_full_names):
    if not maybe_full_names:
        return ()
    names = [_get_name(name) for name in maybe_full_names]
    return namedtuple('full_names', names)(*(
        name if _is_full_name(name) else make_full_name(module_name, name)
        for name in maybe_full_names
    ))


def make_require(module_name, *maybe_full_names):
    return _make_full_names(module_name, maybe_full_names)


def make_provide(module_name, *maybe_full_names):
    return _make_full_names(module_name, maybe_full_names)


class Component:

    require = ()

    provide = None

    def add_arguments(self, parser):
        raise NotImplementedError

    def check_arguments(self, parser, args):
        raise NotImplementedError

    def make(self, require):
        raise NotImplementedError


def bind(component, startup=startup_, component_startup=None, parser_=PARSER):
    component_startup = component_startup or startup

    if _is_method_overridden(component, Component, 'add_arguments'):
        @startup.with_annotations({'parser': parser_, 'return': PARSE})
        @functools.wraps(component.add_arguments)
        def add_arguments(parser):
            return component.add_arguments(parser)

    if _is_method_overridden(component, Component, 'check_arguments'):
        @startup.with_annotations({'parser': PARSER, 'args': ARGS})
        @functools.wraps(component.check_arguments)
        def check_arguments(parser, args):
            return component.check_arguments(parser, args)

    if _is_method_overridden(component, Component, 'make'):
        provide = component.provide
        if isinstance(provide, tuple) and len(provide) == 1:
            provide = provide[0]
        annotations = {'return': provide}

        require = component.require
        if isinstance(require, str):
            require = (require,)
        for full_name in require:
            asserts.precond(_is_full_name(full_name))
            name = _get_name(full_name)
            asserts.precond(name not in annotations)
            annotations[name] = full_name

        @component_startup.with_annotations(annotations)
        @functools.wraps(component.make)
        def make(**require):
            return component.make(DictAsAttrs(require))


def _is_method_overridden(obj, base_cls, method_name):
    if not hasattr(obj, method_name):
        return False
    base_func = getattr(base_cls, method_name)
    method = getattr(obj, method_name)
    func = method.__func__ if isinstance(method, types.MethodType) else method
    return func is not base_func


def vars_as_namespace(varz):
    return DictAsAttrs({
        _get_name(full_name): value for full_name, value in varz.items()
    })


def parse_argv(parser: PARSER, argv: ARGV, _: PARSE) -> ARGS:
    return parser.parse_args(argv[1:])


def main(argv, startup=startup_, component_startup=None):
    startup.set(ARGV, argv)
    startup(parse_argv)
    varz = startup.call()
    if component_startup:
        for name, value in varz.items():
            component_startup.set(name, value)
    return varz[MAIN](varz[ARGS])
