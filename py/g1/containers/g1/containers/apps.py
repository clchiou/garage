__all__ = [
    'main',
    'run',
]

import datetime
import logging
import sys
from pathlib import Path

from startup import startup

from g1.apps import bases as apps_bases
from g1.bases import datetimes
from g1.bases.assertions import ASSERT

from . import bases
from . import builders
from . import formatters
from . import images
from . import pods


@startup
def add_arguments(parser: apps_bases.LABELS.parser) -> apps_bases.LABELS.parse:
    subparsers = add_subparsers_to(parser, 'entity')
    subparsers.add_parser(
        'init',
        **make_help_kwargs('initialize repository'),
    )
    subparsers.add_parser(
        'cleanup',
        **make_help_kwargs('clean up repository'),
    ).add_argument(
        '--grace-period',
        type=bases.parse_period,
        default='24h',
        help='set grace period (default to %(default)s)',
    )
    image_cmds_add_arguments(
        subparsers.add_parser(
            'images', **make_help_kwargs('manage container images')
        )
    )
    pod_cmds_add_arguments(
        subparsers.add_parser(
            'pods', **make_help_kwargs('manage container pods')
        )
    )


def main(args: apps_bases.LABELS.args):
    """Manage containerized application."""
    if args.entity == 'init':
        bases.cmd_init()
        images.cmd_init()
        pods.cmd_init()
    elif args.entity == 'cleanup':
        # Clean up pods before images because pods depend on images but
        # not vice versa.
        expiration = datetimes.utcnow() - args.grace_period
        pods.cmd_cleanup(expiration)
        images.cmd_cleanup(expiration)
    elif args.entity == 'images':
        return image_cmds_main(args)
    elif args.entity == 'pods':
        return pod_cmds_main(args)
    else:
        ASSERT.unreachable('unknown entity: {}', args.entity)
    return 0


def run():
    apps_bases.run(main, prog='ctr')


#
# Image commands.
#

IMAGE_LIST_ALL_COLUMNS = frozenset((
    'id',
    'name',
    'version',
    'tags',
    'ref-count',
    'last-updated',
))
IMAGE_LIST_DEFAULT_COLUMNS = (
    'id',
    'name',
    'version',
    'tags',
    'ref-count',
    'last-updated',
)
IMAGE_LIST_STRINGIFIERS = {
    'tags': ' '.join,
    'last-updated': datetime.datetime.isoformat,
}
ASSERT.issuperset(IMAGE_LIST_ALL_COLUMNS, IMAGE_LIST_DEFAULT_COLUMNS)
ASSERT.issuperset(IMAGE_LIST_ALL_COLUMNS, IMAGE_LIST_STRINGIFIERS)


def image_cmds_add_arguments(parser):
    image_subparsers = add_subparsers_to(parser, 'command')

    image_subparsers.add_parser(
        'build-base',
        **make_help_kwargs('build a base image'),
    ).add_argument(
        'path', type=Path, help='provide base image output path'
    )

    image_subparsers.add_parser(
        'prepare-base-rootfs',
        **make_help_kwargs(
            'prepare rootfs of a base image (useful for testing)'
        ),
    ).add_argument(
        'path', type=Path, help='provide rootfs directory path'
    )

    image_subparsers.add_parser(
        'setup-base-rootfs',
        **make_help_kwargs(
            'set up rootfs of a base image (useful for testing)'
        ),
    ).add_argument(
        'path', type=Path, help='provide rootfs directory path'
    )

    image_subparsers.add_parser(
        'import',
        **make_help_kwargs('import an image archive'),
    ).add_argument(
        'path', type=Path, help='import image archive from this path'
    )

    subparser = image_subparsers.add_parser(
        'list', **make_help_kwargs('list images')
    )
    add_formatter_arguments_to(
        subparser, IMAGE_LIST_ALL_COLUMNS, IMAGE_LIST_DEFAULT_COLUMNS
    )

    subparser = image_subparsers.add_parser(
        'tag', **make_help_kwargs('set tag to an image')
    )
    image_cmds_add_image_arguments_to(subparser)
    subparser.add_argument(
        'new_tag',
        type=images.validate_tag,
        help='provide new image tag',
    )

    image_subparsers.add_parser(
        'remove-tag',
        **make_help_kwargs('remove tag from an image'),
    ).add_argument(
        'tag',
        type=images.validate_tag,
        help='provide image tag for removal',
    )

    subparser = image_subparsers.add_parser(
        'remove', **make_help_kwargs('remove an image from the repository')
    )
    image_cmds_add_image_arguments_to(subparser)


def image_cmds_add_image_arguments_to(parser, required=True):
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument(
        '--id',
        type=images.validate_id,
        help='provide image id',
    )
    group.add_argument(
        '--nv',
        metavar=('NAME', 'VERSION'),
        # Sadly it looks like you can't use ``type`` with ``nargs``.
        nargs=2,
        help='provide image name and version',
    )
    group.add_argument(
        '--tag',
        type=images.validate_tag,
        help='provide image tag',
    )


def make_image_kwargs(args):
    return {
        'image_id': args.id,
        'name': images.validate_name(args.nv[0]) if args.nv else None,
        'version': images.validate_version(args.nv[1]) if args.nv else None,
        'tag': args.tag,
    }


def image_cmds_main(args):
    if args.command == 'build-base':
        builders.cmd_build_base_image(args.path)
    elif args.command == 'prepare-base-rootfs':
        builders.cmd_prepare_base_rootfs(args.path)
    elif args.command == 'setup-base-rootfs':
        builders.cmd_setup_base_rootfs(args.path)
    elif args.command == 'import':
        ASSERT.predicate(args.path, Path.is_file)
        images.cmd_import(args.path)
    elif args.command == 'list':
        formatter = formatters.Formatter(
            **make_formatter_kwargs(args),
            stringifiers=IMAGE_LIST_STRINGIFIERS,
        )
        for row in images.cmd_list():
            formatter.append(row)
        formatter.sort(lambda row: (row['name'], row['version'], row['id']))
        formatter.output(sys.stdout)
    elif args.command == 'tag':
        images.cmd_tag(**make_image_kwargs(args), new_tag=args.new_tag)
    elif args.command == 'remove-tag':
        images.cmd_remove_tag(args.tag)
    elif args.command == 'remove':
        images.cmd_remove(**make_image_kwargs(args))
    else:
        ASSERT.unreachable('unknown image command: {}', args.command)
    return 0


#
# Pod commands.
#


def stringify_last_updated(last_updated):
    return '' if last_updated is None else last_updated.isoformat()


POD_LIST_ALL_COLUMNS = frozenset((
    'id',
    'name',
    'version',
    'images',
    'active',
    'last-updated',
))
POD_LIST_DEFAULT_COLUMNS = (
    'id',
    'name',
    'version',
    'active',
    'last-updated',
)
POD_LIST_STRINGIFIERS = {
    'images': ' '.join,
    'active': lambda active: 'true' if active else 'false',
    'last-updated': stringify_last_updated,
}
ASSERT.issuperset(POD_LIST_ALL_COLUMNS, POD_LIST_DEFAULT_COLUMNS)
ASSERT.issuperset(POD_LIST_ALL_COLUMNS, POD_LIST_STRINGIFIERS)

POD_SHOW_ALL_COLUMNS = frozenset((
    'name',
    'status',
    'last-updated',
))
POD_SHOW_DEFAULT_COLUMNS = (
    'name',
    'status',
    'last-updated',
)
POD_SHOW_STRINGIFIERS = {
    'status': lambda status: '' if status is None else str(status),
    'last-updated': stringify_last_updated,
}
ASSERT.issuperset(POD_SHOW_ALL_COLUMNS, POD_SHOW_DEFAULT_COLUMNS)
ASSERT.issuperset(POD_SHOW_ALL_COLUMNS, POD_SHOW_STRINGIFIERS)


def pod_cmds_add_arguments(parser):
    pod_subparsers = add_subparsers_to(parser, 'command')

    subparser = pod_subparsers.add_parser(
        'list', **make_help_kwargs('list pods')
    )
    add_formatter_arguments_to(
        subparser, POD_LIST_ALL_COLUMNS, POD_LIST_DEFAULT_COLUMNS
    )

    subparser = pod_subparsers.add_parser(
        'show', **make_help_kwargs('show pod status')
    )
    add_formatter_arguments_to(
        subparser, POD_SHOW_ALL_COLUMNS, POD_SHOW_DEFAULT_COLUMNS
    )
    pod_cmds_add_argument_id_to(subparser, positional=True)

    subparser = pod_subparsers.add_parser(
        'cat-config', **make_help_kwargs('show pod config')
    )
    pod_cmds_add_argument_id_to(subparser, positional=True)

    subparser = pod_subparsers.add_parser(
        'run', **make_help_kwargs('run a pod')
    )
    pod_cmds_add_argument_id_to(subparser, positional=False)
    pod_cmds_add_argument_config_to(subparser)

    subparser = pod_subparsers.add_parser(
        'prepare', **make_help_kwargs('prepare a pod')
    )
    pod_cmds_add_argument_id_to(subparser, positional=False)
    pod_cmds_add_argument_config_to(subparser)

    subparser = pod_subparsers.add_parser(
        'run-prepared', **make_help_kwargs('run a prepared pod')
    )
    pod_cmds_add_argument_id_to(subparser, positional=True)

    subparser = pod_subparsers.add_parser(
        'remove', **make_help_kwargs('remove an exited pod')
    )
    pod_cmds_add_argument_id_to(subparser, positional=True)


def pod_cmds_add_argument_id_to(parser, *, positional):
    parser.add_argument(
        'id' if positional else '--id',
        type=pods.validate_id,
        help='set pod id',
    )


def pod_cmds_add_argument_config_to(parser):
    parser.add_argument(
        'config',
        type=Path,
        help='provide path to pod config file',
    )


def pod_cmds_main(args):
    if args.command == 'list':
        formatter = formatters.Formatter(
            **make_formatter_kwargs(args),
            stringifiers=POD_LIST_STRINGIFIERS,
        )
        for row in pods.cmd_list():
            formatter.append(row)
        formatter.sort(lambda row: (row['name'], row['version'], row['id']))
        formatter.output(sys.stdout)
    elif args.command == 'show':
        formatter = formatters.Formatter(
            **make_formatter_kwargs(args),
            stringifiers=POD_SHOW_STRINGIFIERS,
        )
        for row in pods.cmd_show(args.id):
            formatter.append(row)
        formatter.sort(lambda row: row['name'])
        formatter.output(sys.stdout)
    elif args.command == 'cat-config':
        pods.cmd_cat_config(args.id, sys.stdout.buffer)
    elif args.command == 'run':
        pods.cmd_run(
            pod_id=args.id or pods.generate_id(),
            config_path=args.config,
            debug=get_debug(),
        )
    elif args.command == 'prepare':
        pods.cmd_prepare(
            pod_id=args.id or pods.generate_id(),
            config_path=args.config,
        )
    elif args.command == 'run-prepared':
        pods.cmd_run_prepared(pod_id=args.id, debug=get_debug())
    elif args.command == 'remove':
        pods.cmd_remove(args.id)
    else:
        ASSERT.unreachable('unknown pod command: {}', args.command)
    return 0


def get_debug():
    return logging.getLogger().isEnabledFor(logging.DEBUG)


#
# Helpers.
#


def add_subparsers_to(parser, dest):
    # TODO: We need to explicitly set `required` [1].  This bug was
    # fixed but then reverted in Python 3.7 [2].
    # [1] http://bugs.python.org/issue9253
    # [2] https://bugs.python.org/issue26510
    subparsers = parser.add_subparsers()
    subparsers.dest = dest
    subparsers.required = True
    return subparsers


def make_help_kwargs(help_text):
    return {
        'help': help_text,
        'description': '%s%s.' % (help_text[0].upper(), help_text[1:]),
    }


def add_formatter_arguments_to(parser, all_columns, default_columns):
    parser.add_argument(
        '--format',
        choices=sorted(format.name.lower() for format in formatters.Formats),
        default=formatters.Formats.TEXT.name.lower(),
        help='set output format (default: %(default)s)',
    )
    parser.add_argument(
        '--header',
        choices=('true', 'false'),
        default='true',
        help='enable/disable header output (default: %(default)s)',
    )
    action = parser.add_argument(
        '--columns',
        type=lambda columns_str: ASSERT.all(
            list(filter(None, columns_str.split(','))),
            all_columns.__contains__,
        ),
        default=','.join(default_columns),
        help=(
            'set output columns (available columns are: %(all_columns)s) '
            '(default: %(default)s)'
        ),
    )
    action.all_columns = ','.join(sorted(all_columns))


def make_formatter_kwargs(args):
    return {
        'format': formatters.Formats[args.format.upper()],
        'header': args.header == 'true',
        'columns': args.columns,
    }
