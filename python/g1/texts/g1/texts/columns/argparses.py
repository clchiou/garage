__all__ = [
    'columnar_arguments',
    'make_columnar_kwargs',
]

from g1.bases import argparses
from g1.bases import functionals
from g1.bases.assertions import ASSERT

from . import Formats


def columnar_arguments(columns, default_columns):
    return functionals.compose(
        argparses.argument(
            '--format',
            action=argparses.StoreEnumAction,
            default=Formats.TEXT,
            help='set output format (default: %(default_string)s)',
        ),
        argparses.argument(
            '--header',
            action=argparses.StoreBoolAction,
            default=True,
            help='enable/disable header output (default: %(default_string)s)',
        ),
        argparses.begin_argument(
            '--columns',
            type=lambda columns_str: ASSERT.all(
                list(filter(None, columns_str.split(','))),
                columns.__contains__,
            ),
            default=','.join(default_columns),
            help=(
                'set output columns that are comma separated '
                'from available columns: %(columns)s '
                '(default: %(default)s)'
            ),
        ),
        argparses.apply(
            lambda action:
            setattr(action, 'columns', ', '.join(sorted(columns)))
        ),
        argparses.end,
    )


def make_columnar_kwargs(args):
    return {
        'format': args.format,
        'header': args.header,
        'columns': args.columns,
    }
