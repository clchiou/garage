__all__ = [
    'cmd_build',
    'cmd_remove_version',
    'cmd_set_version',
]

import logging

import foreman

from g1 import scripts
from g1.bases import argparses
from g1.bases import functionals
from g1.bases.assertions import ASSERT

import shipyard2
from shipyard2 import params

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
    '--image-version',
    help='overwrite image version (default to the same as pod version)',
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
    if shipyard2.look_like_image_rule(args.rule) and args.image_version:
        ASSERT.equal(args.image_version, args.version)
    LOG.info('build: %s %s', args.rule, args.version)
    scripts.run([
        shipyard2.get_foreman_path(),
        'build',
        *(('--debug', ) if shipyard2.is_debug() else ()),
        *_foreman_make_path_args(),
        *_foreman_make_parameter_args(args),
        args.rule,
    ])
    if shipyard2.look_like_pod_rule(args.rule) and args.also_release:
        label = shipyard2.guess_label_from_rule(args.rule)
        LOG.info('release: %s %s -> %s', label, args.version, args.env)
        _get_envs_dir().set_version(args.env, label, args.version)
    return 0


def _foreman_make_path_args():
    for path in params.get_source_host_paths():
        yield '--path'
        yield path / 'shipyard2' / 'rules'


def _foreman_make_parameter_args(args):
    for name, value in [
        (
            '//releases:sources',
            ','.join(map(str, params.get_source_host_paths())),
        ),
        ('//releases:root', params.get_release_host_path()),
        ('//images/bases:base-version', params.PARAMS.base_version.get()),
        ('//images/bases:version', args.version),
        ('//pods/bases:version', args.version),
    ]:
        yield '--parameter'
        yield '%s=%s' % (name, value)


@argparses.begin_parser(
    'set-version',
    **shipyard2.make_help_kwargs('set pod release version'),
)
@change_version_arguments
@argparses.end
def cmd_set_version(args):
    LOG.info('release: %s %s -> %s', args.label, args.version, args.env)
    _get_envs_dir().set_version(args.env, args.label, args.version)
    return 0


@argparses.begin_parser(
    'remove-version',
    **shipyard2.make_help_kwargs('remove pod release version'),
)
@change_version_arguments
@argparses.end
def cmd_remove_version(args):
    LOG.info('un-release: %s %s -> %s', args.label, args.version, args.env)
    _get_envs_dir().remove_version(args.env, args.label, args.version)
    return 0


def _get_envs_dir():
    return repos.EnvsDir(params.get_release_host_path())
