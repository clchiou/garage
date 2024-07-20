__all__ = [
    'main',
    'run',
]

import json
import sys
from pathlib import Path

from startup import startup

import g1.scripts.parts
from g1.apps import bases
from g1.bases import argparses
from g1.bases.assertions import ASSERT

from . import build
from . import cleanup
from . import repos


@argparses.begin_parser(
    'init',
    **argparses.make_help_kwargs('initialize release repository'),
)
@argparses.end
def cmd_init(args):
    repos.EnvsDir.init(args.release_repo)
    repos.PodDir.init(args.release_repo)
    repos.XarDir.init(args.release_repo)
    repos.BinDir.init(args.release_repo)
    repos.BuilderImageDir.init(args.release_repo)
    repos.ImageDir.init(args.release_repo)
    repos.VolumeDir.init(args.release_repo)
    return 0


@argparses.begin_parser(
    'list',
    **argparses.make_help_kwargs('list build artifacts'),
)
@argparses.end
def cmd_list(args):
    envs_dir = repos.EnvsDir(args.release_repo)
    data = {
        'pod-releases': {
            env: {
                str(pod_dir.label): pod_dir.version
                for pod_dir in envs_dir.sort_pod_dirs(env)
            }
            for env in envs_dir.envs
        },
        'xar-releases': {
            env: {
                str(xar_dir.label): xar_dir.version
                for xar_dir in envs_dir.sort_xar_dirs(env)
            }
            for env in envs_dir.envs
        },
        'bin-releases': {
            env: {
                str(bin_dir.label): bin_dir.version
                for bin_dir in envs_dir.sort_bin_dirs(env)
            }
            for env in envs_dir.envs
        },
    }
    for name, cls in (
        ('pods', repos.PodDir),
        ('xars', repos.XarDir),
        ('bins', repos.BinDir),
        ('builder-images', repos.BuilderImageDir),
        ('images', repos.ImageDir),
        ('volumes', repos.VolumeDir),
    ):
        groups = cls.group_dirs(args.release_repo)
        data[name] = {
            str(label): [obj.version for obj in dir_objects]
            for label, dir_objects in groups.items()
        }
    json.dump(data, sys.stdout, indent=4)
    sys.stdout.write('\n')
    return 0


@argparses.argument(
    '--release-repo',
    type=Path,
    required=True,
    help='provide host path to release repository',
)
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(cmd_init)
@argparses.include(cmd_list)
@argparses.include(build.cmd_build)
@argparses.include(build.cmd_release)
@argparses.include(build.cmd_unrelease)
@argparses.include(build.cmd_remove)
@argparses.include(cleanup.cmd_cleanup)
@argparses.end
def main(
    args: bases.LABELS.args,
    _: g1.scripts.parts.LABELS.setup,
):
    """Release process manager."""
    if args.command == 'init':
        return cmd_init(args)
    elif args.command == 'list':
        return cmd_list(args)
    elif args.command == 'build':
        return build.cmd_build(args)
    elif args.command == 'release':
        return build.cmd_release(args)
    elif args.command == 'unrelease':
        return build.cmd_unrelease(args)
    elif args.command == 'remove':
        return build.cmd_remove(args)
    elif args.command == 'cleanup':
        return cleanup.cmd_cleanup(args)
    else:
        ASSERT.unreachable('unknown command: {}', args.command)
    return 0


def add_arguments(parser: bases.LABELS.parser) -> bases.LABELS.parse:
    argparses.make_argument_parser(main, parser=parser)


def run():
    startup(add_arguments)
    bases.run(main, prog='release')
