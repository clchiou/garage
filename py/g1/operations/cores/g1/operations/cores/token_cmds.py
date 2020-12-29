__all__ = [
    'main',
]

import logging
import sys

from g1.bases import argparses
from g1.bases import oses
from g1.bases.assertions import ASSERT
from g1.containers import models as ctr_models
from g1.texts import columns
from g1.texts.columns import argparses as columns_argparses

from . import models
from . import pod_ops_dirs
from . import tokens

LOG = logging.getLogger(__name__)

_DEFINITION_LIST_COLUMNS = frozenset((
    'token-name',
    'range',
    'values',
))
_DEFINITION_LIST_DEFAULT_COLUMNS = (
    'token-name',
    'range',
    'values',
)
_DEFINITION_LIST_STRINGIFIERS = {
    'range': lambda args: ' '.join(map(str, args)),
    'values': ' '.join,
}
ASSERT.issuperset(_DEFINITION_LIST_COLUMNS, _DEFINITION_LIST_DEFAULT_COLUMNS)
ASSERT.issuperset(_DEFINITION_LIST_COLUMNS, _DEFINITION_LIST_STRINGIFIERS)


@argparses.begin_parser(
    'list-definitions', **argparses.make_help_kwargs('list token definitions')
)
@columns_argparses.columnar_arguments(
    _DEFINITION_LIST_COLUMNS, _DEFINITION_LIST_DEFAULT_COLUMNS
)
@argparses.end
def cmd_list_definitions(args):
    columnar = columns.Columnar(
        **columns_argparses.make_columnar_kwargs(args),
        stringifiers=_DEFINITION_LIST_STRINGIFIERS,
    )
    tokens_database = tokens.make_tokens_database()
    for token_name, definition in tokens_database.get().definitions.items():
        if definition.kind == 'range':
            columnar.append({
                'token-name': token_name,
                'range': definition.args,
                'values': (),
            })
        else:
            ASSERT.equal(definition.kind, 'values')
            columnar.append({
                'token-name': token_name,
                'range': (),
                'values': definition.args,
            })
    columnar.sort(lambda row: row['token-name'])
    columnar.output(sys.stdout)
    return 0


_ASSIGNMENT_LIST_COLUMNS = frozenset((
    'token-name',
    'pod-id',
    'name',
    'value',
))
_ASSIGNMENT_LIST_DEFAULT_COLUMNS = (
    'token-name',
    'pod-id',
    'name',
    'value',
)
_ASSIGNMENT_LIST_STRINGIFIERS = {}
ASSERT.issuperset(_ASSIGNMENT_LIST_COLUMNS, _ASSIGNMENT_LIST_DEFAULT_COLUMNS)
ASSERT.issuperset(_ASSIGNMENT_LIST_COLUMNS, _ASSIGNMENT_LIST_STRINGIFIERS)


@argparses.begin_parser(
    'list-assignments', **argparses.make_help_kwargs('list token assignments')
)
@columns_argparses.columnar_arguments(
    _ASSIGNMENT_LIST_COLUMNS, _ASSIGNMENT_LIST_DEFAULT_COLUMNS
)
@argparses.end
def cmd_list_assignments(args):
    columnar = columns.Columnar(
        **columns_argparses.make_columnar_kwargs(args),
        stringifiers=_ASSIGNMENT_LIST_STRINGIFIERS,
    )
    tokens_database = tokens.make_tokens_database()
    for token_name, assignments in tokens_database.get().assignments.items():
        for assignment in assignments:
            columnar.append({
                'token-name': token_name,
                'pod-id': assignment.pod_id,
                'name': assignment.name,
                'value': assignment.value,
            })
    columnar.sort(
        lambda row:
        (row['token-name'], row['pod-id'], row['name'], row['value'])
    )
    columnar.output(sys.stdout)
    return 0


@argparses.begin_parser(
    'define', **argparses.make_help_kwargs('define a token')
)
@argparses.begin_mutually_exclusive_group(required=True)
@argparses.argument(
    '--range',
    metavar=('LOWER', 'UPPER'),
    nargs=2,
    help='provide range of tokens',
)
@argparses.argument(
    '--value',
    action='append',
    help='add token value',
)
@argparses.end
@argparses.argument(
    'token_name',
    type=models.validate_token_name,
    help='provide name of token',
)
@argparses.end
def cmd_define(args):
    oses.assert_root_privilege()
    if args.range:
        definition = tokens.Tokens.Definition(
            kind='range',
            args=[int(args.range[0]), int(args.range[1])],
        )
    else:
        definition = tokens.Tokens.Definition(
            kind='values',
            args=ASSERT.not_none(args.value),
        )
    tokens_database = tokens.make_tokens_database()
    with tokens_database.writing() as active_tokens:
        if active_tokens.has_definition(args.token_name):
            active_tokens.update_definition(args.token_name, definition)
        else:
            active_tokens.add_definition(args.token_name, definition)
    return 0


@argparses.begin_parser(
    'undefine', **argparses.make_help_kwargs('undefine a token')
)
@argparses.argument(
    'token_name',
    type=models.validate_token_name,
    help='provide name of token',
)
@argparses.end
def cmd_undefine(args):
    oses.assert_root_privilege()
    with pod_ops_dirs.make_ops_dirs().listing_ops_dirs() as active_ops_dirs:
        active_pod_ids = frozenset(
            config.pod_id
            for ops_dir in active_ops_dirs
            for config in ops_dir.metadata.systemd_unit_configs
        )
    tokens_database = tokens.make_tokens_database()
    with tokens_database.writing() as active_tokens:
        if not active_tokens.has_definition(args.token_name):
            LOG.info('skip: tokens undefine: %s', args.token_name)
            return 0
        LOG.info('tokens undefine: %s', args.token_name)
        ASSERT.isdisjoint(
            active_pod_ids, active_tokens.iter_pod_ids(args.token_name)
        )
        active_tokens.remove_definition(args.token_name)
    return 0


# There is no "unassign" command at the moment because it seems
# error-prone to un-assign a token from an active pod.
@argparses.begin_parser(
    'assign', **argparses.make_help_kwargs('assign a token to a pod')
)
@argparses.argument(
    'token_name',
    type=models.validate_token_name,
    help='provide name of token',
)
@argparses.argument(
    'pod_id',
    type=ctr_models.validate_pod_id,
    help='provide pod id',
)
@argparses.argument(
    'name',
    help='provide assignment name',
)
@argparses.argument(
    '--value',
    help='select token value (default: the next available one)',
)
@argparses.end
def cmd_assign(args):
    oses.assert_root_privilege()

    with pod_ops_dirs.make_ops_dirs().listing_ops_dirs() as active_ops_dirs:
        found = False
        for ops_dir in active_ops_dirs:
            for config in ops_dir.metadata.systemd_unit_configs:
                if args.pod_id == config.pod_id:
                    found = True
                    break
            if found:
                break
    if not found:
        LOG.error('tokens assign: pod not found: %s', args.pod_id)
        return 1

    with tokens.make_tokens_database().writing() as active_tokens:
        if not active_tokens.has_definition(args.token_name):
            LOG.error('tokens assign: token not found: %s', args.token_name)
            return 1
        LOG.info('tokens assign: %s -> %s', args.token_name, args.pod_id)
        active_tokens.assign(
            args.token_name, args.pod_id, args.name, args.value
        )

    return 0


@argparses.begin_parser(
    'tokens', **argparses.make_help_kwargs('manage tokens')
)
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(cmd_list_definitions)
@argparses.include(cmd_list_assignments)
@argparses.include(cmd_define)
@argparses.include(cmd_undefine)
@argparses.include(cmd_assign)
@argparses.end
@argparses.end
def main(args):
    if args.command == 'list-definitions':
        return cmd_list_definitions(args)
    elif args.command == 'list-assignments':
        return cmd_list_assignments(args)
    elif args.command == 'define':
        return cmd_define(args)
    elif args.command == 'undefine':
        return cmd_undefine(args)
    elif args.command == 'assign':
        return cmd_assign(args)
    else:
        return ASSERT.unreachable('unknown command: {}', args.command)
