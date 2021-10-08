__all__ = [
    'cmd_build',
    'cmd_release',
    'cmd_unrelease',
]

import json
import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases import argparses
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

select_label_argument = argparses.argument(
    'label',
    type=foreman.Label.parse,
    help='provide pod label',
)

select_version_argument = argparses.argument(
    'version',
    help='provide build artifact version',
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
@select_version_argument
@argparses.end
def cmd_build(args):
    LOG.info('build: %s %s', args.rule, args.version)
    scripts.run([
        REPO_ROOT_PATH / 'shipyard2' / 'scripts' / 'foreman.sh',
        'build',
        *(('--debug', ) if shipyard2.is_debug() else ()),
        *_read_args_file(args.args_file or ()),
        *('--parameter', '//bases:inside-builder-pod=false'),
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
    if args.also_release:
        if _look_like_pod_rule(args.rule):
            release = _get_envs_dir(args).release_pod
        elif _look_like_xar_rule(args.rule):
            release = _get_envs_dir(args).release_xar
        else:
            ASSERT.predicate(args.rule, _look_like_image_rule)
            release = None
        if release:
            label = _guess_label_from_rule(args.rule)
            LOG.info('release: %s %s to %s', label, args.version, args.env)
            release(args.env, label, args.version)
    return 0


def _read_args_file(args_file_paths):
    for path in args_file_paths:
        yield from ASSERT.isinstance(json.loads(path.read_text()), list)


def _look_like_pod_rule(rule):
    return rule.path.parts[0] == shipyard2.RELEASE_PODS_DIR_NAME


def _look_like_xar_rule(rule):
    return rule.path.parts[0] == shipyard2.RELEASE_XARS_DIR_NAME


def _look_like_image_rule(rule):
    return rule.path.parts[0] == shipyard2.RELEASE_IMAGES_DIR_NAME


def _guess_label_from_rule(rule):
    """Guess pod, xar, or image label from build rule.

    For example, //pod/foo:bar/build becomes //foo:bar.
    """
    name_parts = rule.name.parts
    ASSERT(
        len(name_parts) == 2 and name_parts[1] == 'build',
        'expect pod, xar, or image build rule: {}',
        rule,
    )
    return foreman.Label.parse(
        '//%s:%s' % ('/'.join(rule.path.parts[1:]), name_parts[0])
    )


@argparses.begin_parser(
    'release',
    **argparses.make_help_kwargs('release pod at given version'),
)
@select_env_argument
@argparses.argument(
    'type',
    choices=('pods', 'xars'),
    help='provide build artifact type',
)
@select_label_argument
@select_version_argument
@argparses.end
def cmd_release(args):
    LOG.info('release: %s %s to %s', args.label, args.version, args.env)
    if args.type == 'pods':
        release = _get_envs_dir(args).release_pod
    else:
        ASSERT.equal(args.type, 'xars')
        release = _get_envs_dir(args).release_xar
    release(args.env, args.label, args.version)
    return 0


@argparses.begin_parser(
    'unrelease',
    **argparses.make_help_kwargs('undo pod release'),
)
@select_env_argument
@select_label_argument
@argparses.end
def cmd_unrelease(args):
    LOG.info('unrelease: %s from %s', args.label, args.env)
    _get_envs_dir(args).unrelease(args.env, args.label)
    return 0


@argparses.begin_parser(
    'remove',
    **argparses.make_help_kwargs('remove build artifact'),
)
@argparses.argument(
    'type',
    choices=('pods', 'xars', 'builder-images', 'images', 'volumes'),
    help='provide build artifact type',
)
@select_label_argument
@select_version_argument
@argparses.end
def cmd_remove(args):
    if args.type == 'pods':
        dir_object_type = repos.PodDir
        current_versions = _get_envs_dir(args).get_current_pod_versions()
    elif args.type == 'xars':
        dir_object_type = repos.XarDir
        current_versions = _get_envs_dir(args).get_current_xar_versions()
    elif args.type == 'builder-images':
        dir_object_type = repos.BuilderImageDir
        # Builder images are not referenced by pods and thus do not have
        # current versions.
        current_versions = {}
    elif args.type == 'images':
        dir_object_type = repos.ImageDir
        current_versions = repos.get_current_image_versions(args.release_repo)
    else:
        ASSERT.equal(args.type, 'volumes')
        dir_object_type = repos.VolumeDir
        current_versions = repos.PodDir.get_current_volume_versions(
            args.release_repo
        )
    if args.version in current_versions.get(args.label, ()):
        LOG.warning(
            'skip: remove: %s %s %s',
            args.type,
            args.label,
            args.version,
        )
        return 1
    dir_object = dir_object_type.from_relpath(
        args.release_repo,
        args.label.path / args.label.name / args.version,
    )
    LOG.info('remove: %s %s %s', args.type, args.label, args.version)
    dir_object.remove()
    return 0


def _get_envs_dir(args):
    return repos.EnvsDir(args.release_repo)
