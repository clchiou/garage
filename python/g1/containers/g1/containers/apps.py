__all__ = [
    'main',
    'run',
]

import logging
import sys

from startup import startup

import g1.scripts.parts
from g1.apps import bases as apps_bases
from g1.bases import argparses
from g1.bases.assertions import ASSERT
from g1.texts import columns
from g1.texts.columns import argparses as columns_argparses

from . import bases
from . import builders
from . import images
from . import models
from . import pods
from . import xars


@argparses.begin_parser(
    'images', **argparses.make_help_kwargs('manage container images')
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
@argparses.include(images.cmd_cleanup)
@argparses.end
@argparses.end
def cmd_images(args):
    if args.command == 'build-base':
        builders.cmd_build_base_image(
            args.name, args.version, args.output, args.prune_stash_path
        )
    elif args.command == 'prepare-base-rootfs':
        builders.cmd_prepare_base_rootfs(args.path)
    elif args.command == 'setup-base-rootfs':
        builders.cmd_setup_base_rootfs(args.path, args.prune_stash_path)
    elif args.command == 'build':
        images.cmd_build_image(
            args.name, args.version, args.rootfs, args.output
        )
    elif args.command == 'import':
        images.cmd_import(args.path, tag=args.tag)
    elif args.command == 'list':
        columnar = columns.Columnar(
            **columns_argparses.make_columnar_kwargs(args),
            stringifiers=images.IMAGE_LIST_STRINGIFIERS,
        )
        for row in images.cmd_list():
            columnar.append(row)
        columnar.sort(lambda row: (row['name'], row['version'], row['id']))
        columnar.output(sys.stdout)
    elif args.command == 'tag':
        images.cmd_tag(
            **images.make_select_image_kwargs(args),
            new_tag=args.new_tag,
        )
    elif args.command == 'remove-tag':
        images.cmd_remove_tag(args.tag)
    elif args.command == 'remove':
        images.cmd_remove(
            **images.make_select_image_kwargs(args),
            skip_active=args.skip_active,
        )
    elif args.command == 'cleanup':
        images.cmd_cleanup(**bases.make_grace_period_kwargs(args))
    else:
        ASSERT.unreachable('unknown image command: {}', args.command)
    return 0


@argparses.begin_parser(
    'pods', **argparses.make_help_kwargs('manage container pods')
)
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(pods.cmd_list)
@argparses.include(pods.cmd_show)
@argparses.include(pods.cmd_cat_config)
@argparses.include(pods.cmd_generate_id)
@argparses.include(pods.cmd_run)
@argparses.include(pods.cmd_prepare)
@argparses.include(pods.cmd_run_prepared)
@argparses.include(pods.cmd_add_ref)
@argparses.include(pods.cmd_export_overlay)
@argparses.include(pods.cmd_remove)
@argparses.include(pods.cmd_cleanup)
@argparses.end
@argparses.end
def cmd_pods(args):
    command_handlers = {
        'list': lambda: _handle_list(args),
        'show': lambda: _handle_show(args),
        'cat-config': lambda: pods.cmd_cat_config(args.id, sys.stdout.buffer),
        'generate-id': lambda: pods.cmd_generate_id(sys.stdout),
        'run': lambda: pods.cmd_run(
            pod_id=args.id or models.generate_pod_id(),
            config_path=args.config,
            debug=get_debug(),
        ),
        'prepare': lambda: pods.cmd_prepare(
            pod_id=args.id or models.generate_pod_id(),
            config_path=args.config,
        ),
        'run-prepared': lambda: pods.cmd_run_prepared(pod_id=args.id, debug=get_debug()),
        'add-ref': lambda: pods.cmd_add_ref(pod_id=args.id, target_path=args.target),
        'export-overlay': lambda: pods.cmd_export_overlay(
            pod_id=args.id,
            output_path=args.output,
            filter_patterns=args.filter or (),
            debug=get_debug(),
        ),
        'remove': lambda: pods.cmd_remove(args.id),
        'cleanup': lambda: pods.cmd_cleanup(**bases.make_grace_period_kwargs(args)),
    }

    handler = command_handlers.get(args.command)
    if not handler:
        ASSERT.unreachable('unknown pod command: {}', args.command)
    handler()
    return 0

def _handle_list(args):
    columnar = columns.Columnar(
        **columns_argparses.make_columnar_kwargs(args),
        stringifiers=pods.POD_LIST_STRINGIFIERS,
    )
    for row in pods.cmd_list():
        columnar.append(row)
    columnar.sort(lambda row: (row['name'], row['version'], row['id']))
    columnar.output(sys.stdout)

def _handle_show(args):
    columnar = columns.Columnar(
        **columns_argparses.make_columnar_kwargs(args),
        stringifiers=pods.POD_SHOW_STRINGIFIERS,
    )
    for row in pods.cmd_show(args.id):
        columnar.append(row)
    columnar.sort(lambda row: row['name'])
    columnar.output(sys.stdout)


def get_debug():
    return logging.getLogger().isEnabledFor(logging.DEBUG)


@argparses.begin_parser('xars', **argparses.make_help_kwargs('manage xars.'))
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(xars.cmd_install)
@argparses.include(xars.cmd_list)
@argparses.include(xars.cmd_exec)
@argparses.include(xars.cmd_uninstall)
@argparses.include(xars.cmd_cleanup)
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
        columnar = columns.Columnar(
            **columns_argparses.make_columnar_kwargs(args),
            stringifiers=xars.XAR_LIST_STRINGIFIERS,
        )
        for row in xars.cmd_list():
            columnar.append(row)
        columnar.sort(
            lambda row: (row['xar'], row['name'], row['version'], row['id'])
        )
        columnar.output(sys.stdout)
    elif args.command == 'exec':
        xars.cmd_exec(args.name, args.args)
    elif args.command == 'uninstall':
        xars.cmd_uninstall(args.name)
    elif args.command == 'cleanup':
        xars.cmd_cleanup()
    else:
        ASSERT.unreachable('unknown xar command: {}', args.command)
    return 0


@argparses.begin_subparsers_for_subcmds(dest='entity')
@argparses.begin_parser(
    'init', **argparses.make_help_kwargs('initialize repository')
)
@argparses.end
@argparses.begin_parser(
    'cleanup', **argparses.make_help_kwargs('clean up repository')
)
@bases.grace_period_arguments
@argparses.end
@argparses.include(cmd_images)
@argparses.include(cmd_pods)
@argparses.include(cmd_xars)
@argparses.end
def main(
    args: apps_bases.LABELS.args,
    _: g1.scripts.parts.LABELS.setup,
):
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
        grace_period_kwargs = bases.make_grace_period_kwargs(args)
        pods.cmd_cleanup(**grace_period_kwargs)
        xars.cmd_cleanup()
        images.cmd_cleanup(**grace_period_kwargs)
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
