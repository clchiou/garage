__all__ = [
    'cmd_cleanup',
]

import collections
import logging

from g1.bases import argparses
from g1.bases.assertions import ASSERT

from . import repos

LOG = logging.getLogger(__name__)


@argparses.begin_parser(
    'cleanup',
    **argparses.make_help_kwargs('clean up build artifacts'),
)
@argparses.argument(
    'keep',
    type=int,
    help='keep these latest versions (0 to remove all)',
)
@argparses.end
def cmd_cleanup(args):
    ASSERT.greater_or_equal(args.keep, 0)
    LOG.info('clean up pods')
    _cleanup(
        args.keep,
        _get_current_pod_versions(args.release_repo),
        repos.PodDir.group_dirs(args.release_repo),
    )
    LOG.info('clean up xars')
    _cleanup(
        args.keep,
        _get_current_xar_versions(args.release_repo),
        repos.XarDir.group_dirs(args.release_repo),
    )
    LOG.info('clean up builder images')
    # Builder images are not referenced by pods and thus do not have
    # current versions.
    _cleanup(
        args.keep,
        {},
        repos.BuilderImageDir.group_dirs(args.release_repo),
    )
    LOG.info('clean up images')
    _cleanup(
        args.keep,
        _get_current_image_versions(args.release_repo),
        repos.ImageDir.group_dirs(args.release_repo),
    )
    LOG.info('clean up volumes')
    _cleanup(
        args.keep,
        _get_current_volume_versions(args.release_repo),
        repos.VolumeDir.group_dirs(args.release_repo),
    )
    return 0


def _cleanup(to_keep, current_versions, groups):
    for label, dir_objects in groups.items():
        current_version_set = current_versions.get(label, ())
        to_remove = len(dir_objects) - to_keep
        while to_remove > 0 and dir_objects:
            dir_object = dir_objects.pop()
            if dir_object.version not in current_version_set:
                LOG.info('remove: %s %s', label, dir_object.version)
                dir_object.remove()
                to_remove -= 1


def _get_current_pod_versions(repo_path):
    return _get_current_versions_from_envs(
        repo_path, repos.EnvsDir.iter_pod_dirs
    )


def _get_current_xar_versions(repo_path):
    return _get_current_versions_from_envs(
        repo_path, repos.EnvsDir.iter_xar_dirs
    )


def _get_current_versions_from_envs(repo_path, iter_dir_objects):
    current_versions = collections.defaultdict(set)
    envs_dir = repos.EnvsDir(repo_path)
    for env in envs_dir.envs:
        for dir_object in iter_dir_objects(envs_dir, env):
            current_versions[dir_object.label].add(dir_object.version)
    return dict(current_versions)


def _get_current_image_versions(repo_path):
    current_versions = collections.defaultdict(set)
    for labels_and_versions in (
        _get_pod_dep_versions(repo_path, repos.PodDir.iter_image_dirs),
        _get_xar_dep_versions(repo_path),
    ):
        for label, versions in labels_and_versions.items():
            current_versions[label].update(versions)
    return dict(current_versions)


def _get_current_volume_versions(repo_path):
    return _get_pod_dep_versions(repo_path, repos.PodDir.iter_volume_dirs)


def _get_pod_dep_versions(repo_path, iter_dir_objects):
    current_versions = collections.defaultdict(set)
    for pod_dir in repos.PodDir.iter_dirs(repo_path):
        for dir_object in iter_dir_objects(pod_dir):
            current_versions[dir_object.label].add(dir_object.version)
    return dict(current_versions)


def _get_xar_dep_versions(repo_path):
    current_versions = collections.defaultdict(set)
    for xar_dir in repos.XarDir.iter_dirs(repo_path):
        image_dir = xar_dir.get_image_dir()
        if image_dir is not None:
            current_versions[image_dir.label].add(image_dir.version)
    return dict(current_versions)
