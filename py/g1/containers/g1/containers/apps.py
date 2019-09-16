__all__ = [
    'main',
    'run',
]

import logging
import sys

from startup import startup

from g1.apps import bases as apps_bases
from g1.bases import argparses
from g1.bases import datetimes
from g1.bases.assertions import ASSERT

from . import bases
from . import builders
from . import formatters
from . import images
from . import pods
from . import xars


@argparses.begin_parser(
    'images', **bases.make_help_kwargs('manage container images')
)
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(builders.cmd_build_base_image)
@argparses.include(builders.cmd_prepare_base_rootfs)
@argparses.include(builders.cmd_setup_base_rootfs)
@argparses.include(images.cmd_build_image)
@argparses.include(images.cmd_import)
@argparses.include(images.cmd_list)
@argparses.include(images.cmd_tag)
@argparses.include(images.cmd_remove_tag)
@argparses.include(images.cmd_remove)
@argparses.end
@argparses.end
def cmd_images(args):
    if args.command == 'build-base':
        builders.cmd_build_base_image(args.path, args.prune_stash_path)
    elif args.command == 'prepare-base-rootfs':
        builders.cmd_prepare_base_rootfs(args.path)
    elif args.command == 'setup-base-rootfs':
        builders.cmd_setup_base_rootfs(args.path, args.prune_stash_path)
    elif args.command == 'build':
        images.cmd_build_image(
            args.nv[0], args.nv[1], args.rootfs, args.output
        )
    elif args.command == 'import':
        images.cmd_import(args.path, tag=args.tag)
    elif args.command == 'list':
        formatter = formatters.Formatter(
            **bases.make_formatter_kwargs(args),
            stringifiers=images.IMAGE_LIST_STRINGIFIERS,
        )
        for row in images.cmd_list():
            formatter.append(row)
        formatter.sort(lambda row: (row['name'], row['version'], row['id']))
        formatter.output(sys.stdout)
    elif args.command == 'tag':
        images.cmd_tag(
            **images.make_select_image_kwargs(args),
            new_tag=args.new_tag,
        )
    elif args.command == 'remove-tag':
        images.cmd_remove_tag(args.tag)
    elif args.command == 'remove':
        images.cmd_remove(**images.make_select_image_kwargs(args))
    else:
        ASSERT.unreachable('unknown image command: {}', args.command)
    return 0


@argparses.begin_parser(
    'pods', **bases.make_help_kwargs('manage container pods')
)
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(pods.cmd_list)
@argparses.include(pods.cmd_show)
@argparses.include(pods.cmd_cat_config)
@argparses.include(pods.cmd_generate_id)
@argparses.include(pods.cmd_run)
@argparses.include(pods.cmd_prepare)
@argparses.include(pods.cmd_run_prepared)
@argparses.include(pods.cmd_export_overlay)
@argparses.include(pods.cmd_remove)
@argparses.end
@argparses.end
def cmd_pods(args):
    if args.command == 'list':
        formatter = formatters.Formatter(
            **bases.make_formatter_kwargs(args),
            stringifiers=pods.POD_LIST_STRINGIFIERS,
        )
        for row in pods.cmd_list():
            formatter.append(row)
        formatter.sort(lambda row: (row['name'], row['version'], row['id']))
        formatter.output(sys.stdout)
    elif args.command == 'show':
        formatter = formatters.Formatter(
            **bases.make_formatter_kwargs(args),
            stringifiers=pods.POD_SHOW_STRINGIFIERS,
        )
        for row in pods.cmd_show(args.id):
            formatter.append(row)
        formatter.sort(lambda row: row['name'])
        formatter.output(sys.stdout)
    elif args.command == 'cat-config':
        pods.cmd_cat_config(args.id, sys.stdout.buffer)
    elif args.command == 'generate-id':
        pods.cmd_generate_id(sys.stdout)
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
    elif args.command == 'export-overlay':
        pods.cmd_export_overlay(args.id, args.output, args.filter or ())
    elif args.command == 'remove':
        pods.cmd_remove(args.id)
    else:
        ASSERT.unreachable('unknown pod command: {}', args.command)
    return 0


def get_debug():
    return logging.getLogger().isEnabledFor(logging.DEBUG)


@argparses.begin_parser('xars', **bases.make_help_kwargs('manage xars.'))
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(xars.cmd_install)
@argparses.include(xars.cmd_list)
@argparses.include(xars.cmd_exec)
@argparses.include(xars.cmd_uninstall)
@argparses.end
@argparses.end
def cmd_xars(args):
    if args.command == 'install':
        xars.cmd_install(
            **images.make_select_image_kwargs(args),
            xar_name=args.name,
            exec_relpath=args.exec,
        )
    elif args.command == 'list':
        formatter = formatters.Formatter(
            **bases.make_formatter_kwargs(args),
            stringifiers=xars.XAR_LIST_STRINGIFIERS,
        )
        for row in xars.cmd_list():
            formatter.append(row)
        formatter.sort(
            lambda row: (row['xar'], row['name'], row['version'], row['id'])
        )
        formatter.output(sys.stdout)
    elif args.command == 'exec':
        xars.cmd_exec(args.name, args.args)
    elif args.command == 'uninstall':
        xars.cmd_uninstall(args.name)
    else:
        ASSERT.unreachable('unknown xar command: {}', args.command)
    return 0


@argparses.begin_subparsers_for_subcmds(dest='entity')
@argparses.begin_parser(
    'init', **bases.make_help_kwargs('initialize repository')
)
@argparses.end
@argparses.begin_parser(
    'cleanup', **bases.make_help_kwargs('clean up repository')
)
@argparses.argument(
    '--grace-period',
    type=argparses.parse_timedelta,
    default='24h',
    help='set grace period (default to %(default)s)',
)
@argparses.end
@argparses.include(cmd_images)
@argparses.include(cmd_pods)
@argparses.include(cmd_xars)
@argparses.end
def main(args: apps_bases.LABELS.args):
    """Manage containerized application."""
    if args.entity == 'init':
        bases.cmd_init()
        builders.cmd_init()
        images.cmd_init()
        pods.cmd_init()
        xars.cmd_init()
    elif args.entity == 'cleanup':
        # Clean up pods and xars before images because they depend on
        # images but not vice versa.
        expiration = datetimes.utcnow() - args.grace_period
        pods.cmd_cleanup(expiration)
        xars.cmd_cleanup()
        images.cmd_cleanup(expiration)
    elif args.entity == 'images':
        return cmd_images(args)
    elif args.entity == 'pods':
        return cmd_pods(args)
    elif args.entity == 'xars':
        return cmd_xars(args)
    else:
        ASSERT.unreachable('unknown entity: {}', args.entity)
    return 0


def add_arguments(parser: apps_bases.LABELS.parser) -> apps_bases.LABELS.parse:
    argparses.make_argument_parser(main, parser=parser)


def run():
    startup(add_arguments)
    apps_bases.run(main, prog='ctr')
