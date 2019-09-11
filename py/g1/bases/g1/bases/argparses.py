"""Extension of standard library's argparse."""

__all__ = [
    'AppendConstAndValueAction',
    'StoreBoolAction',
    'StoreEnumAction',
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
import dataclasses
import datetime
import enum
import re
import typing

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
    # Import ``copy`` lazily.
    import copy
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


TIMEDELTA_PATTERN = re.compile(
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
                TIMEDELTA_PATTERN.fullmatch(timedelta_str)
            ).groupdict().items()
            if v is not None
        })
    )


#
# Decorator-based ArgumentParser builder.
#
# (A decorator function is a function that returns a decorator.)
#


class Kinds(enum.Enum):

    INCLUDE = enum.auto()

    ARGUMENT_PARSER = enum.auto()

    BEGIN_SUBPARSERS = enum.auto()
    BEGIN_PARSER = enum.auto()

    BEGIN_ARGUMENT_GROUP = enum.auto()

    BEGIN_MUTUALLY_EXCLUSIVE_GROUP = enum.auto()

    ARGUMENT = enum.auto()
    BEGIN_ARGUMENT = enum.auto()

    APPLY = enum.auto()

    END = enum.auto()


@dataclasses.dataclass(frozen=True)
class Instruction:

    kind: Kinds
    func: typing.Callable[..., None] = None
    args: typing.Tuple[typing.Any, ...] = None
    kwargs: typing.Dict[str, typing.Any] = None

    def apply(self, func):
        return func(
            *ASSERT.not_none(self.args),
            **ASSERT.not_none(self.kwargs),
        )


# Where instructions are stashed in a function.
_INSTRUCTIONS = '__g1_bases_argparses__'


def _get_instructions(target):
    return target.__dict__.setdefault(_INSTRUCTIONS, [])


def _add_instruction(target, instruction):
    # Prepend because decorators are applied from inside out.
    _get_instructions(target).insert(0, instruction)
    return target


def _make_simple_decorator_function(kind):
    """Make a decorator function from the given kind."""

    def make_decorator(*args, **kwargs):

        def decorator(target):
            return _add_instruction(
                target, Instruction(kind=kind, args=args, kwargs=kwargs)
            )

        return decorator

    return make_decorator


def include(subtarget):

    def decorator(target):
        return _add_instruction(
            target, Instruction(kind=Kinds.INCLUDE, func=subtarget)
        )

    return decorator


argument_parser = _make_simple_decorator_function(Kinds.ARGUMENT_PARSER)

begin_subparsers = _make_simple_decorator_function(Kinds.BEGIN_SUBPARSERS)
begin_parser = _make_simple_decorator_function(Kinds.BEGIN_PARSER)


def begin_subparsers_for_subcmds(**kwargs):

    #
    # NOTE: We need to explicitly set `required` to true due to [1].
    # This bug was fixed but then reverted in Python 3.7 [2].
    #
    # [1] http://bugs.python.org/issue9253
    # [2] https://bugs.python.org/issue26510
    #
    kwargs.setdefault('required', True)

    def decorator(target):
        return _add_instruction(
            target,
            Instruction(kind=Kinds.BEGIN_SUBPARSERS, args=(), kwargs=kwargs),
        )

    return decorator


begin_argument_group = _make_simple_decorator_function(
    Kinds.BEGIN_ARGUMENT_GROUP
)

begin_mutually_exclusive_group = _make_simple_decorator_function(
    Kinds.BEGIN_MUTUALLY_EXCLUSIVE_GROUP
)

argument = _make_simple_decorator_function(Kinds.ARGUMENT)
begin_argument = _make_simple_decorator_function(Kinds.BEGIN_ARGUMENT)


def apply(func):

    def decorator(target):
        return _add_instruction(
            target, Instruction(kind=Kinds.APPLY, func=func)
        )

    return decorator


def end(target):
    return _add_instruction(target, Instruction(kind=Kinds.END))


def make_argument_parser(target, *, parser=None):
    """Evaluate instructions and return an argument parser."""

    def execute(instructions):
        for instruction in instructions:
            execute_one(instruction)

    def execute_one(instruction):
        if instruction.kind is Kinds.INCLUDE:
            execute(_get_instructions(instruction.func))

        elif instruction.kind is Kinds.ARGUMENT_PARSER:
            push(instruction.apply(argparse.ArgumentParser))

        elif instruction.kind is Kinds.BEGIN_SUBPARSERS:
            push(instruction.apply(tos().add_subparsers))
        elif instruction.kind is Kinds.BEGIN_PARSER:
            push(instruction.apply(tos().add_parser))

        elif instruction.kind is Kinds.BEGIN_ARGUMENT_GROUP:
            push(instruction.apply(tos().add_argument_group))

        elif instruction.kind is Kinds.BEGIN_MUTUALLY_EXCLUSIVE_GROUP:
            push(instruction.apply(tos().add_mutually_exclusive_group))

        elif instruction.kind is Kinds.ARGUMENT:
            instruction.apply(tos().add_argument)
        elif instruction.kind is Kinds.BEGIN_ARGUMENT:
            push(instruction.apply(tos().add_argument))

        elif instruction.kind is Kinds.APPLY:
            instruction.func(tos())

        elif instruction.kind is Kinds.END:
            pop()

        else:
            ASSERT.unreachable('unknown instruction kind: {}', instruction)

    stack = []
    push = stack.append
    pop = lambda: ASSERT.not_empty(stack).pop()
    tos = lambda: ASSERT.not_empty(stack)[-1]

    instructions = _get_instructions(target)

    if parser:
        push(parser)
    else:
        ASSERT(
            instructions and instructions[0].kind is Kinds.ARGUMENT_PARSER,
            'expect Kinds.ARGUMENT_PARSER at first: {}',
            instructions,
        )

    execute(instructions)

    ASSERT(len(stack) == 1, 'expect exactly one left: {}, {}', target, stack)
    return pop()
