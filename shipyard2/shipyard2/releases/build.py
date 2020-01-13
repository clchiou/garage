__all__ = [
    'cmd_build',
    'cmd_remove_version',
    'cmd_set_version',
]

import json
import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases import argparses
from g1.bases import functionals
from g1.bases.assertions import ASSERT

import shipyard2

from . import repos

LOG = logging.getLogger(__name__)

select_env_argument = argparses.argument(
    '--env',
    default='production',
    help='provide environment (default: %(default)s)',
)

change_version_arguments = functionals.compose(
    select_env_argument,
    argparses.argument(
        'label',
        type=foreman.Label.parse,
        help='provide pod label',
    ),
    argparses.argument(
        'version',
        help='provide pod version',
    ),
)


@argparses.begin_parser(
    'build',
    **shipyard2.make_help_kwargs('build pod or image'),
)
@argparses.argument(
    '--also-release',
    action=argparses.StoreBoolAction,
    default=True,
    help='also set pod release version (default: %(default_string)s)',
)
@select_env_argument
@argparses.argument(
    '--args-file',
    type=Path,
    action='append',
    required=True,
    help='add json file of foreman build command-line arguments',
)
@argparses.argument(
    'rule',
    type=foreman.Label.parse,
    help='provide pod or image build rule',
)
@argparses.argument(
    'version',
    help='provide pod or image version',
)
@argparses.end
def cmd_build(args):
    LOG.info('build: %s %s', args.rule, args.version)
    scripts.run([
        shipyard2.get_foreman_path(),
        'build',
        *(('--debug', ) if shipyard2.is_debug() else ()),
        *_read_args_file(args.args_file or ()),
        *(
            '--parameter',
            '//%s:%s=%s' % (
                args.rule.path,
                args.rule.name.with_name('version'),
                args.version,
            ),
        ),
        args.rule,
    ])
    if shipyard2.look_like_pod_rule(args.rule) and args.also_release:
        label = shipyard2.guess_label_from_rule(args.rule)
        LOG.info('release: %s %s -> %s', label, args.version, args.env)
        _get_envs_dir(args).set_version(args.env, label, args.version)
    return 0


def _read_args_file(args_file_paths):
    for path in args_file_paths:
        yield from ASSERT.isinstance(json.loads(path.read_text()), list)


@argparses.begin_parser(
    'set-version',
    **shipyard2.make_help_kwargs('set pod release version'),
)
@change_version_arguments
@argparses.end
def cmd_set_version(args):
    LOG.info('release: %s %s -> %s', args.label, args.version, args.env)
    _get_envs_dir(args).set_version(args.env, args.label, args.version)
    return 0


@argparses.begin_parser(
    'remove-version',
    **shipyard2.make_help_kwargs('remove pod release version'),
)
@change_version_arguments
@argparses.end
def cmd_remove_version(args):
    LOG.info('un-release: %s %s -> %s', args.label, args.version, args.env)
    _get_envs_dir(args).remove_version(args.env, args.label, args.version)
    return 0


def _get_envs_dir(args):
    return repos.EnvsDir(args.release_repo)
