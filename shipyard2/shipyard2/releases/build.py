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

REPO_ROOT_PATH = Path(__file__).parent.parent.parent.parent
ASSERT.predicate(REPO_ROOT_PATH / '.git', Path.is_dir)

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
    **argparses.make_help_kwargs('build pod or image'),
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
        REPO_ROOT_PATH / 'shipyard2' / 'scripts' / 'foreman.sh',
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
    if _look_like_pod_rule(args.rule) and args.also_release:
        label = _guess_label_from_rule(args.rule)
        LOG.info('release: %s %s -> %s', label, args.version, args.env)
        _get_envs_dir(args).set_version(args.env, label, args.version)
    return 0


def _read_args_file(args_file_paths):
    for path in args_file_paths:
        yield from ASSERT.isinstance(json.loads(path.read_text()), list)


def _look_like_pod_rule(rule):
    return rule.path.parts[0] == shipyard2.RELEASE_PODS_DIR_NAME


def _guess_label_from_rule(rule):
    """Guess pod or image label from build rule.

    For example, //pod/foo:bar/build becomes //foo:bar.
    """
    name_parts = rule.name.parts
    ASSERT(
        len(name_parts) == 2 and name_parts[1] == 'build',
        'expect pod or image build rule: {}',
        rule,
    )
    return foreman.Label.parse(
        '//%s:%s' % ('/'.join(rule.path.parts[1:]), name_parts[0])
    )


@argparses.begin_parser(
    'set-version',
    **argparses.make_help_kwargs('set pod release version'),
)
@change_version_arguments
@argparses.end
def cmd_set_version(args):
    LOG.info('release: %s %s -> %s', args.label, args.version, args.env)
    _get_envs_dir(args).set_version(args.env, args.label, args.version)
    return 0


@argparses.begin_parser(
    'remove-version',
    **argparses.make_help_kwargs('remove pod release version'),
)
@change_version_arguments
@argparses.end
def cmd_remove_version(args):
    LOG.info('un-release: %s %s -> %s', args.label, args.version, args.env)
    _get_envs_dir(args).remove_version(args.env, args.label, args.version)
    return 0


def _get_envs_dir(args):
    return repos.EnvsDir(args.release_repo)
