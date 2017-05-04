"""Initialize modules with 1- or 2- stages of startup.

The first startup is the normal, global startup object.  It is called
before main(), which will parse command-line arguments and it will
resolve MAIN and ARGS.  Its dependency graph is:

  PARSER ---> PARSE --+--> ARGS --> CHECK_ARGS
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
    'Fqname',
    'bind',
    'find_closure',
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


LOG = logging.getLogger(__name__)


class Fqname(str):
    """Represent a fully-qualified name."""

    @classmethod
    def parse(cls, fqname_str):
        if isinstance(fqname_str, cls):
            return fqname_str
        asserts.type_of(fqname_str, str)
        index = fqname_str.index(':')
        return cls(fqname_str[:index], fqname_str[index+1:])

    def __new__(cls, module_name, name):
        asserts.type_of(module_name, str)

        # Handle `[name]`-style annotation of name
        read_all = isinstance(name, list) and len(name) == 1
        if read_all:
            name = name[0]
        asserts.type_of(name, str)

        self = super().__new__(cls, '%s:%s' % (module_name, name))
        self.module_name = module_name
        self.name = name
        self._read_all = read_all
        return self

    def __repr__(self):
        return 'Fqname(%r, %r)' % (self.module_name, self.name)

    def as_annotation(self):
        if self._read_all:
            return [self]
        else:
            return self

    def read_all(self):
        return Fqname(self.module_name, [self.name])


ARGS = Fqname(__name__, 'args')
ARGV = Fqname(__name__, 'argv')
CHECK_ARGS = Fqname(__name__, 'check_args')
EXIT_STACK = Fqname(__name__, 'exit_stack')
MAIN = Fqname(__name__, 'main')
PARSE = Fqname(__name__, 'parse')
PARSER = Fqname(__name__, 'parser')

_SYMBOLS = (ARGS, ARGV, CHECK_ARGS, EXIT_STACK, MAIN, PARSE, PARSER)


def make_fqname_tuple(module_name, *maybe_fqnames):
    if not maybe_fqnames:
        return ()
    fqnames = [
        name if isinstance(name, Fqname) else Fqname(module_name, name)
        for name in maybe_fqnames
    ]
    # Make a namedtuple so that you may access fqnames via just their
    # name part
    return namedtuple('fqnames', [fqname.name for fqname in fqnames])(*fqnames)


class Component:

    require = ()

    provide = ()

    order = None

    def add_arguments(self, parser):
        pass

    def check_arguments(self, parser, args):
        pass

    def make(self, require):
        pass


def _get_require_as_tuple(comp):
    # Special case for just a Fqname
    if isinstance(comp.require, Fqname):
        return (comp.require,)
    asserts.type_of(comp.require, tuple)
    return comp.require


def _get_provide_for_annotation(comp):
    # Special case for just a Fqname
    if isinstance(comp.provide, Fqname):
        return comp.provide
    asserts.type_of(comp.provide, tuple)
    # Special case for one-element tuple: We de-tuple it so that your
    # make() function could just return `x` instead of `(x,)`
    if len(comp.provide) == 1:
        return comp.provide[0]
    return comp.provide


def _get_provide_as_tuple(comp):
    # Special case for just a Fqname
    if isinstance(comp.provide, Fqname):
        return (comp.provide,)
    asserts.type_of(comp.provide, tuple)
    return comp.provide


def bind(component, startup=startup_, next_startup=None, parser_=PARSER):
    """Bind a component object to a startup dependency graph."""

    if isinstance(component, type):
        asserts.precond(
            issubclass(component, Component),
            'expect Component subclass, not %r', component,
        )
        component = component()

    asserts.type_of(component, Component)

    next_startup = next_startup or startup

    # Add add_arguments
    if component.order:
        @functools.wraps(component.add_arguments)
        def add_arguments(parser):
            return component.add_arguments(parser)
        add_arguments.__module__ = component.order
    else:
        add_arguments = component.add_arguments
    startup.add_func(add_arguments, {'parser': parser_, 'return': PARSE})

    # Add check_arguments
    if component.order:
        @functools.wraps(component.check_arguments)
        def check_arguments(parser, args):
            return component.check_arguments(parser, args)
        check_arguments.__module__ = component.order
    else:
        check_arguments = component.check_arguments
    startup.add_func(
        check_arguments,
        {'parser': PARSER, 'args': ARGS, 'return': CHECK_ARGS},
    )

    # Populate annotations of make()

    annotations = {
        # Dummies for enforcing order
        '__args': ARGS,
    }
    if next_startup is startup:
        annotations['__check_args'] = CHECK_ARGS

    for fqname in _get_require_as_tuple(component):
        asserts.type_of(fqname, Fqname)
        asserts.not_in(fqname.name, annotations)
        annotations[fqname.name] = fqname.as_annotation()

    provide = _get_provide_for_annotation(component)
    if provide:
        annotations['return'] = provide

    @functools.wraps(component.make)
    def make(__args, __check_args=None, **kwargs):
        return component.make(types.SimpleNamespace(**kwargs))
    if component.order:
        make.__module__ = component.order

    next_startup.add_func(make, annotations)


def find_closure(*comps, ignore=(), ignore_more=_SYMBOLS):
    """Find (and instantiate) dependent components recursively.

    It finds dependent components by searching the modules referred by
    the require list.
    """
    comps = [
        comp if isinstance(comp, Component) else comp()
        for comp in comps
    ]

    ignore = set(ignore)
    ignore.update(ignore_more)

    provide_set = set()
    for comp in comps:
        provide_set.update(_get_provide_as_tuple(comp))

    require_set = set()
    for comp in comps:
        require_set.update(_get_require_as_tuple(comp))
    require_set.difference_update(ignore)
    require_set.difference_update(provide_set)

    while require_set:
        # Find components in modules referred from fqname
        iter_modules = map(
            importlib.import_module,
            # Sort it so that the lookup order is deterministic.
            sorted(set(fqname.module_name for fqname in require_set)),
        )

        original = set(require_set)
        for module in iter_modules:
            for comp_obj_or_class in vars(module).values():

                # Look for component classes in this module
                if (isinstance(comp_obj_or_class, type) and
                        issubclass(comp_obj_or_class, Component)):
                    # Check if this is not what we are looking for
                    provide = _get_provide_as_tuple(comp_obj_or_class)
                    if require_set.isdisjoint(provide):
                        continue
                    # If it is, instantiate it!
                    comp = comp_obj_or_class()

                # Look for component objects in this module
                elif isinstance(comp_obj_or_class, Component):
                    comp = comp_obj_or_class
                    # Check if this is not what we are looking for
                    provide = _get_provide_as_tuple(comp)
                    if require_set.isdisjoint(provide):
                        continue

                else:
                    continue

                comps.append(comp)

                provide_set.update(_get_provide_as_tuple(comp))

                require_set.update(_get_require_as_tuple(comp))
                require_set.difference_update(ignore)
                require_set.difference_update(provide_set)

        if require_set == original:
            raise ValueError(
                'cannot make find components providing %r' % require_set)

    if LOG.isEnabledFor(logging.DEBUG):
        for comp in comps:
            LOG.debug('use component %r', comp)

    return comps


def vars_as_namespace(varz):
    ndict = {}
    for fqname_str, value in varz.items():
        fqname = Fqname.parse(fqname_str)
        if fqname.name in ndict:
            raise ValueError('overwrite name: %r' % fqname.name)
        ndict[fqname.name] = value
    return types.SimpleNamespace(**ndict)


def parse_argv(parser: PARSER, argv: ARGV, _: PARSE) -> ARGS:
    return parser.parse_args(argv[1:])


def main(argv, startup=startup_):
    startup.set(ARGV, argv)
    startup(parse_argv)
    varz = startup.call()
    main_ = varz[MAIN]
    args = varz[ARGS]
    del varz
    return main_(args)
