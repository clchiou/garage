"""Helpers for writing rules under //pods."""

__all__ = [
    'App',
    'Mount',
    'Volume',
    'define_pod',
]

import dataclasses
import logging
import typing
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT
from g1.containers import models as ctr_models
from g1.operations import models as ops_models

import shipyard2
import shipyard2.rules
from shipyard2.rules import releases
from shipyard2.rules import images as _images

# Re-export these.
App = ctr_models.PodConfig.App
Mount = ctr_models.PodConfig.Mount
Volume = ops_models.PodDeployInstruction.Volume

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class PodRules:
    build: foreman.Rule


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
    * Parameter: name/version.
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
    parameter_version = name_prefix + 'version'
    rule_build = name_prefix + 'build'

    (foreman.define_parameter(parameter_version)\
     .with_doc('pod version'))

    images = list(map(foreman.Label.parse, images))

    @foreman.rule(rule_build)
    @foreman.rule.depend('//pods/bases:build')
    @foreman.rule.depend('//releases:build')
    def build(parameters):
        version = ASSERT.not_none(parameters[parameter_version])
        pod_dir_path = releases.get_output_dir_path(parameters, name, version)
        if (
            pod_dir_path / \
            shipyard2.POD_DIR_RELEASE_METADATA_FILENAME
        ).exists():
            LOG.info('skip: build pod: %s %s', name, version)
            return
        LOG.info('build pod: %s %s', name, version)
        try:
            scripts.mkdir(pod_dir_path)
            releases.generate_release_metadata(
                parameters,
                pod_dir_path / shipyard2.POD_DIR_RELEASE_METADATA_FILENAME,
            )
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
        build.depend(str(_images.derive_rule(label)))

    return PodRules(build=build)


def _get_label_name(label):
    return foreman.Label.parse(label).name


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
    releases.dump(
        ops_models.PodDeployInstruction(
            label=str(releases.get_output_label(name)),
            pod_config_template=ctr_models.PodConfig(
                name=name,
                version=version,
                apps=apps,
                images=[
                    ctr_models.PodConfig.Image(
                        name=shipyard2.BASE,
                        version=_images.get_image_version(
                            parameters,
                            shipyard2.BASE_LABEL,
                        ),
                    ),
                    *(
                        ctr_models.PodConfig.Image(
                            name=str(image.name),
                            version=_images.get_image_version(
                                parameters,
                                image,
                            ),
                        ) for image in images
                    ),
                ],
                mounts=mounts,
            ),
            volumes=volumes,
        ),
        pod_dir_path / shipyard2.POD_DIR_DEPLOY_INSTRUCTION_FILENAME,
    )


def _link_images(parameters, pod_dir_path, images):
    scripts.mkdir(pod_dir_path / shipyard2.POD_DIR_IMAGES_DIR_NAME)
    _link(
        shipyard2.POD_DIR_IMAGES_DIR_NAME,
        parameters,
        pod_dir_path,
        shipyard2.BASE_LABEL,
        None,
    )
    for label in images:
        _link(
            shipyard2.POD_DIR_IMAGES_DIR_NAME,
            parameters,
            pod_dir_path,
            label,
            None,
        )


def _link_volumes(parameters, pod_dir_path, volumes):
    scripts.mkdir(pod_dir_path / shipyard2.POD_DIR_VOLUMES_DIR_NAME)
    for volume in volumes:
        _link(
            shipyard2.POD_DIR_VOLUMES_DIR_NAME,
            parameters,
            pod_dir_path,
            foreman.Label.parse(volume.label),
            volume.version,
        )


def _link(sub_dir_name, parameters, pod_dir_path, label, version):
    if sub_dir_name == shipyard2.POD_DIR_IMAGES_DIR_NAME:
        derive = lambda ps, l, _: _images.derive_image_path(ps, l)
    else:
        ASSERT.equal(sub_dir_name, shipyard2.POD_DIR_VOLUMES_DIR_NAME)
        derive = _derive_volume_path
    target_path = ASSERT.predicate(
        derive(parameters, label, version),
        Path.is_file,
    )
    scripts.make_relative_symlink(
        target_path,
        pod_dir_path / sub_dir_name / label.name / target_path.name,
    )


def _derive_volume_path(parameters, label, version):
    return (
        parameters['//releases:root'] / \
        shipyard2.RELEASE_VOLUMES_DIR_NAME /
        label.path /
        label.name /
        version /
        shipyard2.VOLUME_DIR_VOLUME_FILENAME
    )
