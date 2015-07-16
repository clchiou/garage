__all__ = [
    'add_bool_argument',
]

import argparse


def add_bool_argument(parser, *args, **kwargs):
    kwargs = dict(kwargs)  # Make a copy before modifying it...
    kwargs['choices'] = (True, False)
    kwargs['type'] = parse_bool
    parser.add_argument(*args, **kwargs)


def parse_bool(string):
    try:
        return {'true': True, 'false': False}[string.lower()]
    except KeyError:
        raise argparse.ArgumentTypeError(
            'expect either \'true\' or \'false\' instead of %r' % string)
