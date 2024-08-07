"""Manage release repository (not source repository)."""

__all__ = [
    'BinDir',
    'BuilderImageDir',
    'EnvsDir',
    'ImageDir',
    'PodDir',
    'VolumeDir',
    'XarDir',
    'get_current_image_versions',
    'merge_dict_of_sets',
]

import collections
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases import classes
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

    __repr__ = classes.make_repr('repo_path={self.repo_path} envs={self.envs}')

    def __hash__(self):
        return hash((self.repo_path, tuple(self.envs)))

    def __eq__(self, other):
        return self.repo_path == other.repo_path and self.envs == other.envs

    @property
    def _pod_top_path(self):
        return self.repo_path / shipyard2.RELEASE_PODS_DIR_NAME

    @property
    def _xar_top_path(self):
        return self.repo_path / shipyard2.RELEASE_XARS_DIR_NAME

    @property
    def _bin_top_path(self):
        return self.repo_path / shipyard2.RELEASE_BINS_DIR_NAME

    def get_current_pod_versions(self):
        return self._get_current_versions(self.iter_pod_dirs)

    def get_current_xar_versions(self):
        return self._get_current_versions(self.iter_xar_dirs)

    def get_current_bin_versions(self):
        return self._get_current_versions(self.iter_bin_dirs)

    def _get_current_versions(self, iter_dir_objects):
        current_versions = collections.defaultdict(set)
        for env in self.envs:
            for dir_object in iter_dir_objects(env):
                current_versions[dir_object.label].add(dir_object.version)
        return dict(current_versions)

    def iter_pod_dirs(self, env):
        yield from self._iter_dirs(PodDir, self._pod_top_path, env)

    def iter_xar_dirs(self, env):
        yield from self._iter_dirs(XarDir, self._xar_top_path, env)

    def iter_bin_dirs(self, env):
        yield from self._iter_dirs(BinDir, self._bin_top_path, env)

    def _iter_dirs(self, dir_object_type, target_top_path, env):
        ASSERT.in_(env, self.envs)
        # NOTE: rglob does NOT traverse into symlink directory (which is
        # good in this case).
        for link_path in (self.top_path / env).rglob('*'):
            if not link_path.is_symlink():
                continue
            target_path = link_path.resolve()
            # XXX Is there a better way to match path prefix?
            if str(target_path).startswith(str(target_top_path)):
                yield dir_object_type(target_top_path, target_path)

    def sort_pod_dirs(self, env):
        return _sort_by_path(self.iter_pod_dirs(env))

    def sort_xar_dirs(self, env):
        return _sort_by_path(self.iter_xar_dirs(env))

    def sort_bin_dirs(self, env):
        return _sort_by_path(self.iter_bin_dirs(env))

    def release_pod(self, env, label, version):
        return self._release(PodDir, self._pod_top_path, env, label, version)

    def release_xar(self, env, label, version):
        return self._release(XarDir, self._xar_top_path, env, label, version)

    def release_bin(self, env, label, version):
        return self._release(BinDir, self._bin_top_path, env, label, version)

    def _release(self, dir_object_type, target_top_path, env, label, version):
        relpath = label.path / label.name
        link_path = self.top_path / env / relpath
        dir_object = dir_object_type(
            target_top_path,
            target_top_path / relpath / version,
        )
        scripts.rm(link_path)
        scripts.make_relative_symlink(dir_object.path, link_path)

    def unrelease(self, env, label):
        ASSERT.in_(env, self.envs)
        _remove_file_and_maybe_parents(
            self.top_path / env / label.path / label.name,
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

    @classmethod
    def from_relpath(cls, repo_path, relpath):
        top_path = repo_path / cls._TOP_DIR_NAME
        return cls(top_path, top_path / relpath)

    def __init__(self, top_path, path):
        ASSERT.predicate(path, Path.is_dir)
        ASSERT.predicate(path / self._FILENAME, Path.is_file)
        self.top_path = top_path
        self.path = path

    __repr__ = classes.make_repr('path={self.path}')

    def __hash__(self):
        return hash((self.top_path, self.path))

    def __eq__(self, other):
        return self.top_path == other.top_path and self.path == other.path

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

    @classmethod
    def get_current_image_versions(cls, repo_path):
        return cls._get_current_versions(repo_path, cls.iter_image_dirs)

    @classmethod
    def get_current_volume_versions(cls, repo_path):
        return cls._get_current_versions(repo_path, cls.iter_volume_dirs)

    @classmethod
    def _get_current_versions(cls, repo_path, iter_dir_objects):
        current_versions = collections.defaultdict(set)
        for pod_dir in cls.iter_dirs(repo_path):
            for dir_object in iter_dir_objects(pod_dir):
                current_versions[dir_object.label].add(dir_object.version)
        return dict(current_versions)

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


class XarDir(_Base):

    _TOP_DIR_NAME = shipyard2.RELEASE_XARS_DIR_NAME
    _FILENAME = shipyard2.XAR_DIR_RELEASE_METADATA_FILENAME

    @classmethod
    def get_current_image_versions(cls, repo_path):
        current_versions = collections.defaultdict(set)
        for xar_dir in cls.iter_dirs(repo_path):
            image_dir = xar_dir.get_image_dir()
            if image_dir is not None:
                current_versions[image_dir.label].add(image_dir.version)
        return dict(current_versions)

    def __init__(self, top_path, path):
        ASSERT.predicate(path, Path.is_dir)
        for name, predicate in (
            (shipyard2.XAR_DIR_RELEASE_METADATA_FILENAME, Path.is_file),
            (shipyard2.XAR_DIR_DEPLOY_INSTRUCTION_FILENAME, Path.is_file),
        ):
            ASSERT.predicate(path / name, predicate)
        ASSERT.any(
            (
                path / shipyard2.XAR_DIR_IMAGE_FILENAME,
                path / shipyard2.XAR_DIR_ZIPAPP_FILENAME,
            ),
            Path.is_file,
        )
        super().__init__(top_path, path)

    def get_image_dir(self):
        link_path = self.path / shipyard2.XAR_DIR_IMAGE_FILENAME
        if not link_path.is_symlink():
            return None
        return ImageDir(
            self.top_path.parent / shipyard2.RELEASE_IMAGES_DIR_NAME,
            link_path.resolve().parent,
        )


class BinDir(_Base):

    _TOP_DIR_NAME = shipyard2.RELEASE_BINS_DIR_NAME
    _FILENAME = shipyard2.BIN_DIR_RELEASE_METADATA_FILENAME

    def __init__(self, top_path, path):
        ASSERT.predicate(path, Path.is_dir)
        names = {
            shipyard2.BIN_DIR_RELEASE_METADATA_FILENAME,
            path.parent.name,
        }
        # For now, we cannot use "release.json" as a binary file name.
        ASSERT.predicate(names, lambda ns: len(ns) == 2)
        for name in names:
            ASSERT.predicate(path / name, Path.is_file)
        super().__init__(top_path, path)


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


def get_current_image_versions(repo_path):
    return merge_dict_of_sets(
        PodDir.get_current_image_versions(repo_path),
        XarDir.get_current_image_versions(repo_path),
    )


def merge_dict_of_sets(*dicts_of_sets):
    output = collections.defaultdict(set)
    for dict_of_sets in dicts_of_sets:
        for key, value_set in dict_of_sets.items():
            output[key].update(value_set)
    return dict(output)
