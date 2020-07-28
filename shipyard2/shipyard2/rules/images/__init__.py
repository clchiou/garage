"""Helpers for writing rules under //images."""

__all__ = [
    'define_image',
    'define_xar_image',
    'derive_image_path',
    'derive_rule',
    'generate_exec_wrapper',
    'get_image_version',
]

import dataclasses
import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT
from g1.containers import models
from g1.containers import scripts as ctr_scripts

import shipyard2
import shipyard2.rules

from . import build_image
from . import merge_image
from . import utils

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


@dataclasses.dataclass(frozen=True)
class ImageRules:
    build: foreman.Rule
    merge: foreman.Rule


def define_image(
    *,
    name,
    rules,
    default_filters=merge_image.DEFAULT_FILTERS,
    filters=(),
):
    """Define an application image.

    This defines:
    * Parameter: name/builder-id.
    * Parameter: name/builder-images.
    * Parameter: name/keep-builder.
    * Parameter: name/version.
    * Rule: name/build.
    * Rule: name/merge.

    NOTE: These rules are generally run in the host system, not inside a
    builder pod.
    """
    ASSERT.not_empty(rules)
    name_prefix = shipyard2.rules.canonicalize_name_prefix(name)
    parameter_builder_id = name_prefix + 'builder-id'
    parameter_builder_images = name_prefix + 'builder-images'
    parameter_keep_builder = name_prefix + 'keep-builder'
    parameter_version = name_prefix + 'version'
    rule_build = name_prefix + 'build'
    rule_merge = name_prefix + 'merge'

    (foreman.define_parameter(parameter_builder_id)\
     .with_doc('builder pod id (optional)'))

    (foreman.define_parameter(parameter_builder_images)\
     .with_doc(
         'list of intermediate builder images where each image is '
         'either: "id:XXX", "nv:XXX:YYY", or "tag:XXX"'
     )
     .with_type(list)
     .with_parse(utils.parse_images_parameter)
     .with_default([]))

    (foreman.define_parameter.bool_typed(parameter_keep_builder)\
     .with_doc('whether to keep the output builder image')
     .with_default(False))

    (foreman.define_parameter(parameter_version)\
     .with_doc('image version'))

    @foreman.rule(rule_build)
    @foreman.rule.depend('//images/bases:base/build')
    @foreman.rule.depend('//images/bases:build')
    @foreman.rule.depend('//releases:build')
    def build(parameters):
        version = ASSERT.not_none(parameters[parameter_version])
        output = utils.get_builder_image_path(parameters, name)
        if output.exists():
            LOG.info('skip: build image: %s %s %s', name, version, output)
            return
        LOG.info('build image: %s %s %s', name, version, output)
        builder_id = parameters[parameter_builder_id]
        if builder_id is None:
            builder_id = models.generate_pod_id()
            LOG.info('generate builder pod id: %s', builder_id)
        scripts.mkdir(output.parent)
        build_image.build_image(
            parameters=parameters,
            builder_id=builder_id,
            builder_images=parameters[parameter_builder_images],
            name=name,
            version=version,
            # We need a full label; convert ':name' to '//path:name'.
            rules=[
                foreman.Label.parse(rule, implicit_path=foreman.get_relpath())
                for rule in rules
            ],
            output=output,
        )
        utils.chown(output)

    @foreman.rule(rule_merge)
    @foreman.rule.depend('//images/bases:build')
    @foreman.rule.depend('//releases:build')
    @foreman.rule.depend(rule_build)
    def merge(parameters):
        version = ASSERT.not_none(parameters[parameter_version])
        output = utils.get_image_path(parameters, name)
        if output.exists():
            LOG.info('skip: merge image: %s %s %s', name, version, output)
            return
        LOG.info('merge image: %s %s %s', name, version, output)
        scripts.mkdir(output.parent)
        merge_image.merge_image(
            name=name,
            version=version,
            builder_images=parameters[parameter_builder_images],
            default_filters=default_filters,
            filters=filters,
            output=output,
        )
        utils.chown(output)
        if not parameters[parameter_keep_builder]:
            LOG.info('remove output builder image: %s %s', name, version)
            with scripts.using_sudo():
                ctr_scripts.ctr_remove_image(
                    models.PodConfig.Image(
                        name=utils.get_builder_name(name),
                        version=version,
                    )
                )
            scripts.rm(utils.get_builder_image_path(parameters, name))

    return ImageRules(build=build, merge=merge)


def define_xar_image(
    *,
    name,
    rules,
    default_filters=merge_image.DEFAULT_XAR_FILTERS,
    filters=(),
):
    """Define a XAR image.

    This is basically the same as define_image but with a different list
    of default filters.
    """
    return define_image(
        name=name,
        rules=rules,
        default_filters=default_filters,
        filters=filters,
    )


def derive_rule(label):
    """Derive image build rule from image label."""
    return foreman.Label(
        shipyard2.RELEASE_IMAGES_DIR_NAME / label.path,
        label.name / 'merge',
    )


def derive_image_path(parameters, label):
    """Derive image path under release repo from image label."""
    return (
        parameters['//releases:root'] / \
        shipyard2.RELEASE_IMAGES_DIR_NAME /
        label.path /
        label.name /
        get_image_version(parameters, label) /
        shipyard2.IMAGE_DIR_IMAGE_FILENAME
    )


def get_image_version(parameters, label):
    """Read image version parameter."""
    return parameters['//%s/%s:%s/version' % (
        shipyard2.RELEASE_IMAGES_DIR_NAME,
        label.path,
        label.name,
    )]


_WRAPPER_SCRIPT_TEMPLATE = '''\
#!/usr/bin/env bash

set -o errexit -o nounset -o pipefail

readonly ROOT="$(realpath "$(dirname "${{BASH_SOURCE[-1]}}"){wrapper_to_root}")"

readonly LIB_DIRS=(
  "${{ROOT}}/usr/local/lib"
  "${{ROOT}}/usr/lib"
  "${{ROOT}}/usr/lib/x86_64-linux-gnu"
)
for lib_dir in "${{LIB_DIRS[@]}}"; do
  LD_LIBRARY_PATH="${{LD_LIBRARY_PATH:-}}${{LD_LIBRARY_PATH:+:}}${{lib_dir}}"
done
export LD_LIBRARY_PATH

export PATH="${{ROOT}}/usr/local/bin${{PATH:+:}}${{PATH:-}}"

exec "${{ROOT}}/{exec_relpath}" "${{@}}"
'''


def generate_exec_wrapper(exec_relpath, wrapper_relpath):
    """Generate a wrapper script for the executable of a XAR.

    To load shared libraries inside XAR image, the wrapper script sets
    LD_LIBRARY_PATH before launching the executable.
    """
    ASSERT.not_predicate(Path(exec_relpath), Path.is_absolute)
    wrapper_path = (
        Path('/') / \
        ASSERT.not_predicate(Path(wrapper_relpath), Path.is_absolute)
    )
    wrapper_script = _WRAPPER_SCRIPT_TEMPLATE.format(
        wrapper_to_root=''.join(('/..', ) * (len(wrapper_path.parts) - 2)),
        exec_relpath=exec_relpath,
    )
    with scripts.using_sudo():
        scripts.write_bytes(wrapper_script.encode('utf-8'), wrapper_path)
        scripts.run(['chmod', '0755', wrapper_path])
