"""Initialize modules with 1- or 2- stages of startup.

The first startup is the normal, global startup object.  It is called
before main(), which will parse command-line arguments and it will
resolve MAIN and ARGS.  Its dependency graph is:

  PARSER ---> PARSE --+--> ARGS
                      |
              ARGV ---+

  MAIN

The `components` model is most useful for creating of static singleton
objects, which traditionally are implemented by global objects that
usually result in cyclic imports.  This means that if the number of the
objects you would like to create is not known statically, you might need
to put some extra work.

NOTE: 'fqname' stands for 'fully-qualified name'.
"""

__all__ = [
    'ARGS',
    'EXIT_STACK',
    'MAIN',
    'PARSE',
    'PARSER',
    'Component',
    'bind',
    'find_closure',
    'fqname',
    'main',
    'make_fqname_tuple',
    'vars_as_namespace',
]

import functools
import importlib
import logging
import types
from collections import namedtuple

from startup import startup as startup_

from garage import asserts
from garage.collections import DictViewAttrs, unique


LOG = logging.getLogger(__name__)


def fqname(module_name, name):
    return '%s:%s' % (module_name, name)


def _is_fqname(name):
    return ':' in name


def _get_module_name(fqname_):
    return fqname_[:fqname_.index(':')]


def _get_name(maybe_fqname):
    return maybe_fqname[maybe_fqname.rfind(':')+1:]


ARGS = fqname(__name__, 'args')
ARGV = fqname(__name__, 'argv')
EXIT_STACK = fqname(__name__, 'exit_stack')
MAIN = fqname(__name__, 'main')
PARSE = fqname(__name__, 'parse')
PARSER = fqname(__name__, 'parser')

_SYMBOLS = (ARGS, ARGV, EXIT_STACK, MAIN, PARSE, PARSER)


def make_fqname_tuple(module_name, *maybe_fqnames):
    if not maybe_fqnames:
        return ()
    names = [_get_name(name) for name in maybe_fqnames]
    return namedtuple('fqnames', names)(*(
        name if _is_fqname(name) else fqname(module_name, name)
        for name in maybe_fqnames
    ))


class Component:

    require = ()

    aliases = None

    provide = None

    def add_arguments(self, parser):
        asserts.fail()

    def check_arguments(self, parser, args):
        asserts.fail()

    def make(self, require):
        asserts.fail()


def bind(component, startup=startup_, next_startup=None, parser_=PARSER):
    next_startup = next_startup or startup

    if _is_method_overridden(component, Component, 'add_arguments'):
        @functools.wraps(component.add_arguments)
        def add_arguments(parser):
            return component.add_arguments(parser)
        startup.add_func(add_arguments, {'parser': parser_, 'return': PARSE})

    if _is_method_overridden(component, Component, 'check_arguments'):
        @functools.wraps(component.check_arguments)
        def check_arguments(parser, args):
            return component.check_arguments(parser, args)
        startup.add_func(check_arguments, {'parser': PARSER, 'args': ARGS})

    if _is_method_overridden(component, Component, 'make'):
        provide = component.provide
        if isinstance(provide, tuple) and len(provide) == 1:
            provide = provide[0]
        annotations = {'return': provide}

        aliases = getattr(component, 'aliases', None)

        require = component.require
        if isinstance(require, str):
            require = (require,)
        for fqname_ in require:
            asserts.precond(_is_fqname(fqname_))
            if aliases and fqname_ in aliases:
                name = aliases[fqname_]
            else:
                name = _get_name(fqname_)
            asserts.precond(name not in annotations)
            annotations[name] = fqname_

        @functools.wraps(component.make)
        def make(**require):
            return component.make(DictViewAttrs(require))
        next_startup.add_func(make, annotations)


def _is_method_overridden(obj, base_cls, method_name):
    if not hasattr(obj, method_name):
        return False
    base_func = getattr(base_cls, method_name)
    method = getattr(obj, method_name)
    func = method.__func__ if isinstance(method, types.MethodType) else method
    return func is not base_func


def find_closure(*comps, ignore=(), ignore_more=_SYMBOLS):
    """Find (and make) dependent components recursively by convention."""
    comps = list(comps)
    comp_classes = {type(comp) for comp in comps}

    ignore = set(ignore)
    ignore.update(ignore_more)

    def _update(target, source):
        if source is None:
            pass
        elif isinstance(source, str):
            target.add(source)
        else:
            target.update(source)

    provide_set = set()
    for comp in comps:
        _update(provide_set, comp.provide)

    require_set = set()
    for comp in comps:
        _update(require_set, comp.require)
    require_set.difference_update(ignore)
    require_set.difference_update(provide_set)

    while require_set:
        iter_modules = map(
            importlib.import_module,
            # Sort it so that the lookup order is deterministic.
            unique(map(_get_module_name, sorted(require_set)))
        )
        original = set(require_set)
        for module in iter_modules:
            for comp_class in vars(module).values():
                if (not isinstance(comp_class, type) or
                        not issubclass(comp_class, Component) or
                        comp_class in comp_classes or
                        comp_class.provide is None or
                        require_set.isdisjoint(comp_class.provide)):
                    continue
                comps.append(comp_class())
                comp_classes.add(comp_class)
                _update(provide_set, comp_class.provide)
                _update(require_set, comp_class.require)
                require_set.difference_update(ignore)
                require_set.difference_update(provide_set)
        if require_set == original:
            raise ValueError(
                'cannot make find components providing %r' % require_set)

    if LOG.isEnabledFor(logging.DEBUG):
        for comp in comps:
            LOG.debug('use component %r', comp)

    return comps


def vars_as_namespace(varz, aliases=None):
    ndict = {}
    for fqname_, value in varz.items():
        if aliases and fqname_ in aliases:
            name = aliases[fqname_]
        else:
            name = _get_name(fqname_)
        if name in ndict:
            raise ValueError('overwrite name: %r' % name)
        ndict[name] = value
    return DictViewAttrs(ndict)


def parse_argv(parser: PARSER, argv: ARGV, _: PARSE) -> ARGS:
    return parser.parse_args(argv[1:])


def main(argv, startup=startup_):
    startup.set(ARGV, argv)
    startup(parse_argv)
    varz = startup.call()
    return varz[MAIN](varz[ARGS])
