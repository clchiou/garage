"""Extension of standard library's argparse."""

__all__ = [
    'StoreBoolAction',
    'StoreEnumAction',
    'parse_timedelta',
]

import argparse
import builtins
import datetime
import re

from .assertions import ASSERT


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
