__all__ = [
    'main',
]

import sys

from g1.bases import argparses
from g1.bases import oses
from g1.bases.assertions import ASSERT
from g1.texts import columns
from g1.texts.columns import argparses as columns_argparses

from . import envs
from . import models

_ENV_LIST_COLUMNS = frozenset((
    'name',
    'value',
))
_ENV_LIST_DEFAULT_COLUMNS = (
    'name',
    'value',
)
ASSERT.issuperset(_ENV_LIST_COLUMNS, _ENV_LIST_DEFAULT_COLUMNS)


@argparses.begin_parser(
    'list',
    **argparses.make_help_kwargs('list environment variables'),
)
@columns_argparses.columnar_arguments(
    _ENV_LIST_COLUMNS, _ENV_LIST_DEFAULT_COLUMNS
)
@argparses.end
def cmd_list(args):
    columnar = columns.Columnar(**columns_argparses.make_columnar_kwargs(args))
    for name, value in envs.load().items():
        columnar.append({'name': name, 'value': value})
    columnar.output(sys.stdout)
    return 0


@argparses.begin_parser(
    'set',
    **argparses.make_help_kwargs('create or update an environment variable'),
)
@argparses.argument(
    'name',
    type=models.validate_env_name,
    help='environment variable name',
)
@argparses.argument(
    'value',
    # TODO: What restriction should we put on the value string format?
    help='environment variable value',
)
@argparses.end
def cmd_set(args):
    oses.assert_root_privilege()
    env_dict = envs.load()
    env_dict[args.name] = args.value
    envs.save(env_dict)
    return 0


@argparses.begin_parser(
    'remove',
    **argparses.make_help_kwargs('remove an environment variable'),
)
@argparses.argument(
    'name',
    type=models.validate_env_name,
    help='environment variable name',
)
@argparses.end
def cmd_remove(args):
    oses.assert_root_privilege()
    env_dict = envs.load()
    if env_dict.pop(args.name, None) is not None:
        envs.save(env_dict)
    return 0


@argparses.begin_parser(
    'envs', **argparses.make_help_kwargs('manage environment variables')
)
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(cmd_list)
@argparses.include(cmd_set)
@argparses.include(cmd_remove)
@argparses.end
@argparses.end
def main(args):
    if args.command == 'list':
        return cmd_list(args)
    elif args.command == 'set':
        return cmd_set(args)
    elif args.command == 'remove':
        return cmd_remove(args)
    else:
        return ASSERT.unreachable('unknown command: {}', args.command)
