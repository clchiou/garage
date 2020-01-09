"""Helpers for writing rules under //pods."""

__all__ = [
    'App',
    'Mount',
    'Volume',
    'define_pod',
]

import dataclasses
import json
import logging
import os.path
import typing
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT
from g1.containers import pods

import shipyard2
import shipyard2.rules
import shipyard2.rules.images
import shipyard2.rules.volumes

# Re-export these.
App = pods.PodConfig.App
Mount = pods.PodConfig.Mount

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Volume:
    label: str
    version: str
    target: str
    read_only: bool = True


@dataclasses.dataclass(frozen=True)
class PodRules:
    build: foreman.Rule


@dataclasses.dataclass(frozen=True)
class ReleaseMetadata:

    @dataclasses.dataclass(frozen=True)
    class Source:
        url: str
        revision: str
        dirty: bool

    sources: typing.List[Source]


@dataclasses.dataclass(frozen=True)
class DeployInstruction:
    pod_config_template: pods.PodConfig
    volumes: typing.List[Volume]


def define_pod(
    *,
    name: str,
    apps: typing.List[App] = (),
    images: typing.List[str] = (),
    mounts: typing.List[Mount] = (),
    volumes: typing.List[Volume] = (),
):
    """Define a pod.

    This defines:
    * Rule: name/build.  NOTE: This rule is generally run in the host
      system, not inside a builder pod.
    """
    ASSERT(len(images) <= 1, 'expect at most one image per pod for now: {}')
    # Let's require absolute release labels (because it is quite hard to
    # derive label path for images and volumes from pod label).
    ASSERT.all(images, lambda label: label.startswith('//'))
    ASSERT.all(volumes, lambda volume: volume.label.startswith('//'))
    ASSERT(
        len(set(map(_get_label_name, images))) == len(images),
        'expect unique image names: {}',
        images,
    )
    ASSERT(
        len(set(_get_label_name(volume.label) for volume in volumes)) == \
        len(volumes),
        'expect unique volume names: {}',
        volumes,
    )
    name_prefix = shipyard2.rules.canonicalize_name_prefix(name)
    rule_build = name_prefix + 'build'

    @foreman.rule(rule_build)
    @foreman.rule.depend('//pods/bases:build')
    @foreman.rule.depend('//releases:build')
    def build(parameters):
        version = parameters['//pods/bases:version']
        pod_dir_path = _get_pod_dir_path(parameters, name, version)
        if (
            pod_dir_path / \
            shipyard2.POD_DIR_RELEASE_METADATA_FILENAME
        ).exists():
            LOG.info('skip: build pod: %s %s', name, version)
            return
        LOG.info('build pod: %s %s', name, version)
        try:
            scripts.mkdir(pod_dir_path)
            _generate_release_metadata(parameters, pod_dir_path)
            _generate_deploy_instruction(
                parameters=parameters,
                pod_dir_path=pod_dir_path,
                name=name,
                version=version,
                apps=apps,
                images=images,
                mounts=mounts,
                volumes=volumes,
            )
            _link_images(parameters, pod_dir_path, images)
            _link_volumes(parameters, pod_dir_path, volumes)
        except Exception:
            # Roll back on error.
            scripts.rm(pod_dir_path, recursive=True)
            raise

    for label in images:
        build.depend(_parse_image_label(label))

    return PodRules(build=build)


def _get_label_name(label):
    return foreman.Label.parse(label).name


def _get_pod_dir_path(parameters, name, version):
    return (
        parameters['//releases:root'] / \
        foreman.get_relpath() /
        name /
        version
    )


def _parse_image_label(label):
    """Convert an image label to a label under shipyard2/rules."""
    label = foreman.Label.parse(label)
    return str(foreman.Label('images' / label.path, label.name / 'merge'))


def _generate_release_metadata(parameters, pod_dir_path):
    _dump(
        ReleaseMetadata(
            sources=[
                _git_get_source(source)
                for source in parameters['//releases:sources']
            ],
        ),
        pod_dir_path / shipyard2.POD_DIR_RELEASE_METADATA_FILENAME,
    )


def _git_get_source(source):
    with scripts.using_cwd(source), scripts.doing_capture_output():
        return ReleaseMetadata.Source(
            url=_git_get_url(source),
            revision=_git_get_revision(),
            dirty=_git_get_dirty(),
        )


def _git_get_url(source):
    proc = scripts.run(['git', 'remote', '--verbose'])
    for remote in proc.stdout.decode('utf8').split('\n'):
        remote = remote.split()
        if remote[0] == 'origin':
            return remote[1]
    return ASSERT.unreachable('expect remote origin: {}', source)


def _git_get_revision():
    proc = scripts.run(['git', 'log', '-1', '--format=format:%H'])
    return proc.stdout.decode('ascii').strip()


def _git_get_dirty():
    proc = scripts.run(['git', 'status', '--porcelain'])
    for status in proc.stdout.decode('utf8').split('\n'):
        # Be careful of empty line!
        if status and not status.startswith('  '):
            return True
    return False


def _generate_deploy_instruction(
    *,
    parameters,
    pod_dir_path,
    name,
    version,
    apps,
    images,
    mounts,
    volumes,
):
    _dump(
        DeployInstruction(
            pod_config_template=pods.PodConfig(
                name=name,
                version=version,
                apps=apps,
                images=[
                    pods.PodConfig.Image(
                        name=shipyard2.BASE,
                        version=parameters['//images/bases:base-version'],
                    ),
                    pods.PodConfig.Image(
                        name=str(foreman.Label.parse(images[0]).name),
                        version=parameters['//images/bases:version'],
                    ),
                ],
                mounts=mounts,
            ),
            volumes=volumes,
        ),
        pod_dir_path / shipyard2.POD_DIR_DEPLOY_INSTRUCTION_FILENAME,
    )


def _dump(obj, path):
    scripts.write_bytes(
        json.dumps(dataclasses.asdict(obj), indent=4).encode('ascii'),
        path,
    )


def _link_images(parameters, pod_dir_path, images):
    scripts.mkdir(pod_dir_path / shipyard2.POD_DIR_IMAGES_DIR_NAME)
    _link(
        shipyard2.POD_DIR_IMAGES_DIR_NAME,
        parameters,
        pod_dir_path,
        '//bases:%s' % shipyard2.BASE,
        parameters['//images/bases:base-version'],
    )
    version = parameters['//images/bases:version']
    for label in images:
        _link(
            shipyard2.POD_DIR_IMAGES_DIR_NAME,
            parameters,
            pod_dir_path,
            label,
            version,
        )


def _link_volumes(parameters, pod_dir_path, volumes):
    scripts.mkdir(pod_dir_path / shipyard2.POD_DIR_VOLUMES_DIR_NAME)
    for volume in volumes:
        _link(
            shipyard2.POD_DIR_VOLUMES_DIR_NAME,
            parameters,
            pod_dir_path,
            volume.label,
            volume.version,
        )


def _link(subdir_name, parameters, pod_dir_path, label, version):
    if subdir_name == shipyard2.POD_DIR_IMAGES_DIR_NAME:
        get_path = shipyard2.rules.images.get_image_path
    else:
        ASSERT.equal(subdir_name, shipyard2.POD_DIR_VOLUMES_DIR_NAME)
        get_path = shipyard2.rules.volumes.get_volume_path
    target_path = ASSERT.predicate(
        ASSERT.predicate(
            get_path(parameters, label, version),
            Path.is_absolute,
        ),
        # Err out when target file does not exist.
        Path.is_file,
    )
    link_path = (
        pod_dir_path / \
        subdir_name /
        _get_label_name(label) /
        target_path.name
    )
    # Use os.path.relpath because Path.relative_to can't derive this
    # type of relative path.
    target_relpath = os.path.relpath(target_path, link_path.parent)
    scripts.mkdir(link_path.parent)
    with scripts.using_cwd(link_path.parent):
        scripts.ln(target_relpath, link_path.name)
