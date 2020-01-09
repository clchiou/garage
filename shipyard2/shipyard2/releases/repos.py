"""Manage release repository (not source repository)."""

__all__ = [
    'BuilderImageDir',
    'EnvsDir',
    'ImageDir',
    'PodDir',
    'VolumeDir',
]

import collections
import os.path
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2


def _remove_file_and_maybe_parents(path, parent_path):
    scripts.rm(path, recursive=path.is_dir())
    with scripts.using_cwd(parent_path):
        scripts.rmdir(
            path.parent.relative_to(parent_path),
            parents=True,
            ignore_fail_on_non_empty=True,
        )


class EnvsDir:

    @staticmethod
    def init(repo_path):
        scripts.mkdir(repo_path / shipyard2.RELEASE_ENVS_DIR_NAME)

    def __init__(self, repo_path):
        self.repo_path = repo_path
        self.top_path = self.repo_path / shipyard2.RELEASE_ENVS_DIR_NAME
        self.envs = sorted(
            p.name for p in self.top_path.iterdir() if p.is_dir()
        )

    @property
    def _pod_top_path(self):
        return self.repo_path / shipyard2.RELEASE_PODS_DIR_NAME

    def iter_pod_dirs(self, env):
        ASSERT.in_(env, self.envs)
        # NOTE: rglob does NOT traverse into symlink directory (which is
        # good in this case).
        for link_path in (self.top_path / env).rglob('*'):
            if link_path.is_symlink():
                yield PodDir(self._pod_top_path, link_path.resolve())

    def sort_pod_dirs(self, env):
        return _sort_by_path(self.iter_pod_dirs(env))

    def set_version(self, env, label, version):
        relpath = label.path / label.name / version
        link_path = self.top_path / env / relpath
        pod_dir = PodDir(self._pod_top_path, self._pod_top_path / relpath)
        # We create a new env directory if env is not in self.envs.
        scripts.mkdir(link_path.parent)
        if link_path.is_symlink():
            scripts.rm(link_path)
        # Use os.path.relpath because Path.relative_to can't derive this
        # type of relative path.
        target_relpath = os.path.relpath(pod_dir.path, link_path.parent)
        with scripts.using_cwd(link_path.parent):
            scripts.ln(target_relpath, link_path.name)

    def remove_version(self, env, label, version):
        ASSERT.in_(env, self.envs)
        _remove_file_and_maybe_parents(
            self.top_path / env / label.path / label.name / version,
            self.top_path / env,
        )


class _Base:

    _TOP_DIR_NAME = None
    _FILENAME = None

    @classmethod
    def init(cls, repo_path):
        scripts.mkdir(repo_path / cls._TOP_DIR_NAME)

    @classmethod
    def iter_dirs(cls, repo_path):
        top_path = repo_path / cls._TOP_DIR_NAME
        for path in top_path.rglob(cls._FILENAME):
            yield cls(top_path, path.parent)

    @classmethod
    def sort_dirs(cls, repo_path):
        return _sort_by_path(cls.iter_dirs(repo_path))

    @classmethod
    def group_dirs(cls, repo_path):
        groups = collections.defaultdict(list)
        for dir_object in cls.sort_dirs(repo_path):
            groups[dir_object.label].append(dir_object)
        return dict(groups)

    def __init__(self, top_path, path):
        ASSERT.predicate(path, Path.is_dir)
        ASSERT.predicate(path / self._FILENAME, Path.is_file)
        self.top_path = top_path
        self.path = path

    @property
    def label(self):
        relpath = self.path.parent.relative_to(self.top_path)
        label_path = relpath.parent
        label_name = relpath.name
        return foreman.Label.parse('//%s:%s' % (label_path, label_name))

    @property
    def version(self):
        return self.path.name

    def remove(self):
        _remove_file_and_maybe_parents(
            self.path,
            self.top_path,
        )


class PodDir(_Base):

    _TOP_DIR_NAME = shipyard2.RELEASE_PODS_DIR_NAME
    _FILENAME = shipyard2.POD_DIR_RELEASE_METADATA_FILENAME

    def __init__(self, top_path, path):
        ASSERT.predicate(path, Path.is_dir)
        for name, predicate in (
            (shipyard2.POD_DIR_RELEASE_METADATA_FILENAME, Path.is_file),
            (shipyard2.POD_DIR_DEPLOY_INSTRUCTION_FILENAME, Path.is_file),
            (shipyard2.POD_DIR_IMAGES_DIR_NAME, Path.is_dir),
            (shipyard2.POD_DIR_VOLUMES_DIR_NAME, Path.is_dir),
        ):
            ASSERT.predicate(path / name, predicate)
        super().__init__(top_path, path)

    def iter_image_dirs(self):
        yield from self._iter_deps(
            ImageDir,
            self.top_path.parent / shipyard2.RELEASE_IMAGES_DIR_NAME,
            shipyard2.POD_DIR_IMAGES_DIR_NAME,
            shipyard2.IMAGE_DIR_IMAGE_FILENAME,
        )

    def iter_volume_dirs(self):
        yield from self._iter_deps(
            VolumeDir,
            self.top_path.parent / shipyard2.RELEASE_VOLUMES_DIR_NAME,
            shipyard2.POD_DIR_VOLUMES_DIR_NAME,
            shipyard2.VOLUME_DIR_VOLUME_FILENAME,
        )

    def _iter_deps(self, dir_object_type, top_path, dir_name, filename):
        for dir_path in (self.path / dir_name).iterdir():
            link_path = dir_path / filename
            if link_path.is_symlink():
                yield dir_object_type(
                    top_path,
                    link_path.resolve().parent,
                )


class BuilderImageDir(_Base):

    _TOP_DIR_NAME = shipyard2.RELEASE_IMAGES_DIR_NAME
    _FILENAME = shipyard2.IMAGE_DIR_BUILDER_IMAGE_FILENAME

    def remove(self):
        _remove_file_and_maybe_parents(
            self.path / self._FILENAME,
            self.top_path,
        )


class ImageDir(_Base):

    _TOP_DIR_NAME = shipyard2.RELEASE_IMAGES_DIR_NAME
    _FILENAME = shipyard2.IMAGE_DIR_IMAGE_FILENAME

    def remove(self):
        _remove_file_and_maybe_parents(
            self.path / self._FILENAME,
            self.top_path,
        )


class VolumeDir(_Base):
    _TOP_DIR_NAME = shipyard2.RELEASE_VOLUMES_DIR_NAME
    _FILENAME = shipyard2.VOLUME_DIR_VOLUME_FILENAME


def _sort_by_path(iterator):
    return sorted(iterator, key=lambda obj: obj.path)
