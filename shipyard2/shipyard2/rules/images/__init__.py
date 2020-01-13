"""Helpers for writing rules under //images."""

__all__ = [
    'define_image',
]

import dataclasses
import logging

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

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
    filters=(),
):
    """Define an application image.

    This defines:
    * Parameter: name/builder-id.
    * Parameter: name/builder-images.
    * Parameter: name/version.
    * Parameter: name/image.
    * Parameter: name/builder-image.
    * Rule: name/build.
    * Rule: name/merge.

    NOTE: These rules are generally run in the host system, not inside a
    builder pod.
    """
    ASSERT.not_empty(rules)
    name_prefix = shipyard2.rules.canonicalize_name_prefix(name)
    parameter_builder_id = name_prefix + 'builder-id'
    parameter_builder_images = name_prefix + 'builder-images'
    parameter_version = name_prefix + 'version'
    parameter_image = name_prefix + 'image'
    parameter_builder_image = name_prefix + 'builder-image'
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
     .with_parse(utils.parse_image_list_parameter)
     .with_default([]))

    (foreman.define_parameter(parameter_version)\
     .with_doc('image version'))

    (foreman.define_parameter.path_typed(parameter_image)\
     .with_doc('host path to image output')
     .with_derive(utils.make_derive_image_path(name)))

    (foreman.define_parameter.path_typed(parameter_builder_image)\
     .with_doc('host path to builder image output')
     .with_derive(utils.make_derive_builder_image_path(name)))

    @foreman.rule(rule_build)
    @foreman.rule.depend('//images/bases:base/build')
    @foreman.rule.depend('//images/bases:build')
    @foreman.rule.depend('//releases:build')
    def build(parameters):
        version = ASSERT.not_none(parameters[parameter_version])
        output = parameters[parameter_builder_image]
        if output.exists():
            LOG.info('skip: build image: %s %s %s', name, version, output)
            return
        LOG.info('build image: %s %s %s', name, version, output)
        builder_id = parameters[parameter_builder_id]
        if builder_id is None:
            builder_id = utils.ctr_generate_pod_id()
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
        output = parameters[parameter_image]
        if output.exists():
            LOG.info('skip: merge image: %s %s %s', name, version, output)
            return
        LOG.info('merge image: %s %s %s', name, version, output)
        scripts.mkdir(output.parent)
        merge_image.merge_image(
            name=name,
            version=version,
            builder_images=parameters[parameter_builder_images],
            filters=filters,
            output=output,
        )
        utils.chown(output)

    return ImageRules(build=build, merge=merge)
