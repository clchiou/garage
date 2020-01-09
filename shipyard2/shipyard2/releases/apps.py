__all__ = [
    'main',
    'run',
]

import json
import sys

from startup import startup

import g1.scripts.parts
from g1.apps import bases
from g1.bases import argparses
from g1.bases.assertions import ASSERT

import shipyard2
from shipyard2 import params

from . import build
from . import cleanup
from . import repos


@argparses.begin_parser(
    'init',
    **shipyard2.make_help_kwargs('initialize release repository'),
)
@argparses.end
def cmd_init():
    repo_path = params.get_release_host_path()
    repos.EnvsDir.init(repo_path)
    repos.PodDir.init(repo_path)
    repos.BuilderImageDir.init(repo_path)
    repos.ImageDir.init(repo_path)
    repos.VolumeDir.init(repo_path)
    return 0


@argparses.begin_parser(
    'list',
    **shipyard2.make_help_kwargs('list build artifacts'),
)
@argparses.end
def cmd_list():
    repo_path = params.get_release_host_path()
    envs_dir = repos.EnvsDir(repo_path)
    data = {
        'envs': {
            env: {
                str(pod_dir.label): pod_dir.version
                for pod_dir in envs_dir.sort_pod_dirs(env)
            }
            for env in envs_dir.envs
        },
    }
    for name, cls in (
        ('pods', repos.PodDir),
        ('builder-images', repos.BuilderImageDir),
        ('images', repos.ImageDir),
        ('volumes', repos.VolumeDir),
    ):
        groups = cls.group_dirs(repo_path)
        data[name] = {
            str(label): [obj.version for obj in dir_objects]
            for label, dir_objects in groups.items()
        }
    json.dump(data, sys.stdout, indent=4)
    sys.stdout.write('\n')
    return 0


@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(cmd_init)
@argparses.include(cmd_list)
@argparses.include(build.cmd_build)
@argparses.include(build.cmd_set_version)
@argparses.include(build.cmd_remove_version)
@argparses.include(cleanup.cmd_cleanup)
@argparses.end
def main(
    args: bases.LABELS.args,
    _: g1.scripts.parts.LABELS.setup,
):
    """Release process manager."""
    if args.command == 'init':
        return cmd_init()
    elif args.command == 'list':
        return cmd_list()
    elif args.command == 'build':
        return build.cmd_build(args)
    elif args.command == 'set-version':
        return build.cmd_set_version(args)
    elif args.command == 'remove-version':
        return build.cmd_remove_version(args)
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
