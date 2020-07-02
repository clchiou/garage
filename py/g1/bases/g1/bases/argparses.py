"""Extension of standard library's argparse."""

__all__ = [
    'AppendConstAndValueAction',
    'StoreBoolAction',
    'StoreEnumAction',
    'make_help_kwargs',
    'parse_name_value_pair',
    'parse_timedelta',
    # Decorator-based ArgumentParser builder.
    'make_argument_parser',
    # Decorator functions.
    'apply',
    'argument',
    'argument_parser',
    'begin_argument',
    'begin_argument_group',
    'begin_mutually_exclusive_group',
    'begin_parser',
    'begin_subparsers',
    'begin_subparsers_for_subcmds',
    'end',
    'include',
]

import argparse
import builtins
import copy
import datetime
import enum
import json
import re

from .assertions import ASSERT


class AppendConstAndValueAction(argparse.Action):

    def __init__(
        self,
        option_strings,
        dest,
        *,
        nargs=None,
        const,
        default=None,
        type=None,  # pylint: disable=redefined-builtin
        choices=None,
        required=False,
        help=None,  # pylint: disable=redefined-builtin
        metavar=None,
    ):
        ASSERT.not_in(nargs, (0, '?'))
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=nargs,
            const=const,
            default=default,
            type=type,
            choices=choices,
            required=required,
            help=help,
            metavar=metavar,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        items = _copy_items(getattr(namespace, self.dest, None))
        items.append((self.const, values))
        setattr(namespace, self.dest, items)


def _copy_items(items):
    if items is None:
        return []
    if type(items) is list:  # pylint: disable=unidiomatic-typecheck
        return items[:]
    return copy.copy(items)


class StoreBoolAction(argparse.Action):

    TRUE = 'true'
    FALSE = 'false'

    def __init__(
        self,
        option_strings,
        dest,
        default=None,
        required=False,
        help=None,  # pylint: disable=redefined-builtin
        metavar=None,
    ):
        ASSERT.in_(default, (None, True, False))
        # We want ``default`` to be a parsed value (True or False), but
        # ``choices`` a list of formatted strings ("true" and "false").
        # To have this, we do NOT assign ``type`` field, and defer real
        # parsing until __call__.
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            choices=[self.TRUE, self.FALSE],
            required=required,
            help=help,
            metavar=metavar,
        )
        # We create this formatted default string because ``default`` is
        # a parsed value.
        self.default_string = {True: self.TRUE, False: self.FALSE}.get(default)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values == self.TRUE)


class StoreEnumAction(argparse.Action):

    def __init__(
        self,
        option_strings,
        dest,
        default=None,
        type=None,  # pylint: disable=redefined-builtin
        required=False,
        help=None,  # pylint: disable=redefined-builtin
        metavar=None,
    ):
        if type is None:
            type = builtins.type(ASSERT.not_none(default))
        # Do NOT assign ``type`` field here for the same reason above.
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            choices=list(map(self.__format, type)),
            required=required,
            help=help,
            metavar=metavar,
        )
        # Create ``default_string`` for the same reason above.
        if default is not None:
            self.default_string = self.__format(default)
        else:
            self.default_string = None
        self.__type = type

    @staticmethod
    def __format(member):
        return member.name.lower().replace('_', '-')

    def __parse(self, name):
        return self.__type[name.replace('-', '_').upper()]

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, self.__parse(values))


def make_help_kwargs(help_text):
    return {
        'help': help_text,
        'description': '%s%s.' % (help_text[0].upper(), help_text[1:]),
    }


def parse_name_value_pair(arg_str, *, parsers=()):
    """Parse a "NAME=VALUE"-formatted pair.

    Parsers are applied sequentially until the first success.

    This is intended to be used when the set of NAME strings cannot be
    easily specified in advance (thus parsers are applied sequentially
    rather than keyed by the NAME string).
    """
    name, value_str = arg_str.split('=', maxsplit=1)
    for parser in parsers:
        try:
            return name, parser(value_str)
        except Exception:
            pass
    return name, _parse_value(value_str)


_IDENTIFIER_PATTERN = re.compile(r'[a-zA-Z_]\w*')
_NON_IDENTIFIERS = frozenset(('true', 'false'))


def _parse_value(value_str):
    """Default VALUE string parse function."""
    # Make a special case for identifier-like strings.
    if (
        _IDENTIFIER_PATTERN.fullmatch(value_str)
        and value_str not in _NON_IDENTIFIERS
    ):
        return value_str
    else:
        return json.loads(value_str)


_TIMEDELTA_PATTERN = re.compile(
    r'(?:(?P<days>\d+)d)?'
    r'(?:(?P<hours>\d+)h)?'
    r'(?:(?P<minutes>\d+)m)?'
    r'(?:(?P<seconds>\d+)s)?'
)


def parse_timedelta(timedelta_str):
    return datetime.timedelta(
        **ASSERT.not_empty({
            k: int(v)
            for k, v in ASSERT.not_none(
                _TIMEDELTA_PATTERN.fullmatch(timedelta_str)
            ).groupdict().items()
            if v is not None
        })
    )


#
# Decorator-based ArgumentParser builder.
#
# (A decorator function is a function that returns a decorator.)
#


class _Ops(enum.Enum):
    # PUSH m ( n -- n m )
    PUSH = enum.auto()
    # DUP ( n -- n n )
    DUP = enum.auto()
    # DROP ( n -- )
    DROP = enum.auto()
    # APPLY f n ( a1 a2 ... an -- f(a1, a2, ..., an) )
    APPLY = enum.auto()
    # CALL args kwargs ( f -- f(*args, **kwargs) )
    CALL = enum.auto()


def _execute(stack, instructions):
    """Execute instructions of a simple stack machine.

    Each instruction is either (opcode, operands...) or (target, ).
    """
    for instruction in instructions:
        _execute_one(stack, instruction)


def _execute_one(stack, instruction):
    if instruction[0] is _Ops.PUSH:
        stack.append(instruction[1])
    elif instruction[0] is _Ops.DUP:
        stack.append(stack[-1])
    elif instruction[0] is _Ops.DROP:
        stack.pop()
    elif instruction[0] is _Ops.APPLY:
        arity = ASSERT.less_or_equal(instruction[2], len(stack))
        stack[-arity:] = [instruction[1](*stack[-arity:])]
    elif instruction[0] is _Ops.CALL:
        stack[-1] = stack[-1](*instruction[1], **instruction[2])
    else:
        _execute(stack, _get_instructions(instruction[0]))


# Where instructions are stashed in a function.
_INSTRUCTIONS = '__g1_bases_argparses__'


def _get_instructions(target):
    return target.__dict__.setdefault(_INSTRUCTIONS, [])


def _add_instructions(target, *more_instructions):
    # Prepend because decorators are applied from inside out.
    _get_instructions(target)[0:0] = more_instructions
    return target


def _make_method_call(method_name, *, keep_result=True):

    def make_decorator(*args, **kwargs):

        def decorator(target):
            return _add_instructions(
                target,
                (_Ops.DUP, ),
                (_Ops.PUSH, method_name),
                (_Ops.APPLY, getattr, 2),
                (_Ops.CALL, args, kwargs),
                *([] if keep_result else [(_Ops.DROP, )]),
            )

        return decorator

    return make_decorator


def include(include_target):

    def decorator(target):
        return _add_instructions(target, (include_target, ))

    return decorator


def argument_parser(*args, **kwargs):

    def decorator(target):
        return _add_instructions(
            target,
            (_Ops.PUSH, argparse.ArgumentParser),
            (_Ops.CALL, args, kwargs),
        )

    return decorator


begin_subparsers = _make_method_call('add_subparsers')
begin_parser = _make_method_call('add_parser')


def begin_subparsers_for_subcmds(**kwargs):
    # NOTE: We need to explicitly set `required` to true due to [1].
    # This bug was fixed but then reverted in Python 3.7 [2].
    # [1] http://bugs.python.org/issue9253
    # [2] https://bugs.python.org/issue26510
    kwargs.setdefault('required', True)
    return begin_subparsers(**kwargs)


begin_argument_group = _make_method_call('add_argument_group')

begin_mutually_exclusive_group = _make_method_call(
    'add_mutually_exclusive_group'
)

argument = _make_method_call('add_argument', keep_result=False)
begin_argument = _make_method_call('add_argument')


def apply(func):

    def decorator(target):
        return _add_instructions(
            target,
            (_Ops.DUP, ),
            (_Ops.APPLY, func, 1),
            (_Ops.DROP, ),
        )

    return decorator


def end(target):
    return _add_instructions(target, (_Ops.DROP, ))


def make_argument_parser(target, *, parser=None):
    stack = []
    if parser:
        stack.append(parser)
    _execute(stack, _get_instructions(target))
    ASSERT(len(stack) == 1, 'expect exactly one left: {}, {}', target, stack)
    return stack[0]
