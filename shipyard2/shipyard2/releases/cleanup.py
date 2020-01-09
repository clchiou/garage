__all__ = [
    'cmd_cleanup',
]

import logging

from g1.bases import argparses
from g1.bases.assertions import ASSERT

import shipyard2
from shipyard2 import params

from . import repos

LOG = logging.getLogger(__name__)


@argparses.begin_parser(
    'cleanup',
    **shipyard2.make_help_kwargs('clean up build artifacts'),
)
@argparses.argument(
    'keep',
    type=int,
    help='keep these latest versions (0 to remove all)',
)
@argparses.end
def cmd_cleanup(args):
    ASSERT.greater_or_equal(args.keep, 0)
    repo_path = params.get_release_host_path()
    LOG.info('clean up pods')
    _cleanup(
        args.keep,
        _get_current_pod_versions(repo_path),
        repos.PodDir.group_dirs(repo_path),
    )
    LOG.info('clean up builder images')
    # Builder images are not referenced by pods and thus do not have
    # current versions.
    _cleanup(args.keep, {}, repos.BuilderImageDir.group_dirs(repo_path))
    LOG.info('clean up images')
    _cleanup(
        args.keep,
        _get_current_image_versions(repo_path),
        repos.ImageDir.group_dirs(repo_path),
    )
    LOG.info('clean up volumes')
    _cleanup(
        args.keep,
        _get_current_volume_versions(repo_path),
        repos.VolumeDir.group_dirs(repo_path),
    )
    return 0


def _cleanup(to_keep, current_versions, groups):
    for label, dir_objects in groups.items():
        current_version = current_versions.get(label)
        to_remove = len(dir_objects) - to_keep
        while to_remove > 0 and dir_objects:
            dir_object = dir_objects.pop()
            if dir_object.version != current_version:
                LOG.info('remove: %s %s', label, dir_object.version)
                dir_object.remove()
                to_remove -= 1


def _get_current_pod_versions(repo_path):
    current_versions = {}
    envs_dir = repos.EnvsDir(repo_path)
    for env in envs_dir.envs:
        for pod_dir in envs_dir.iter_pod_dirs(env):
            ASSERT.setitem(current_versions, pod_dir.label, pod_dir.version)
    return current_versions


def _get_current_image_versions(repo_path):
    return _get_pod_dep_versions(repo_path, repos.PodDir.iter_image_dirs)


def _get_current_volume_versions(repo_path):
    return _get_pod_dep_versions(repo_path, repos.PodDir.iter_volume_dirs)


def _get_pod_dep_versions(repo_path, iter_dir_objects):
    current_versions = {}
    for pod_dir in repos.PodDir.iter_dirs(repo_path):
        for dir_object in iter_dir_objects(pod_dir):
            ASSERT.setitem(
                current_versions, dir_object.label, dir_object.version
            )
    return current_versions
