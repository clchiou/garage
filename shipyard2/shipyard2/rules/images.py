"""Helpers for writing rules under //images."""

__all__ = [
    'IMAGE_FILENAME',
    'define_image',
    'get_image_path',
]

import dataclasses
import getpass
import logging

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2
import shipyard2.rules

LOG = logging.getLogger(__name__)

IMAGE_FILENAME = 'image.tar.gz'


@dataclasses.dataclass(frozen=True)
class ImageRules:
    build: foreman.Rule


# NOTE: This function is generally called in the host system, not inside
# a builder pod.
def get_image_path(parameters, name, version):
    return (
        parameters['//releases:root'] / \
        foreman.get_relpath() /
        name /
        version /
        IMAGE_FILENAME
    )


def _get_builder_name(name):
    return name + '-builder'


def _get_builder_image_path(image_path):
    return image_path.with_name('builder-image.tar.gz')


def define_image(
    name,
    rules,
):
    """Define an application image.

    This defines:
    * Rule: name/build.  NOTE: This rule is generally run in the host
      system, not inside a builder pod.
    """
    ASSERT.not_empty(rules)
    name_prefix = shipyard2.rules.canonicalize_name_prefix(name)
    rule_build = name_prefix + 'build'

    @foreman.rule(rule_build)
    @foreman.rule.depend('//images/bases:build')
    @foreman.rule.depend('//releases:build')
    def build(parameters):
        version = parameters['//images/bases:version']
        image_path = get_image_path(parameters, name, version)
        if image_path.exists():
            LOG.info('skip: build image: %s %s', name, version)
            return
        LOG.info('build image: %s %s', name, version)
        scripts.mkdir(image_path.parent)
        try:
            _build(parameters, name, rules, image_path)
            _merge(parameters, name, image_path)
        finally:
            scripts.rm(_get_builder_image_path(image_path))
            scripts.run([
                parameters['//images/bases:ctr'],
                'images',
                'remove',
                *('--nv', _get_builder_name(name), version),
            ])
            if image_path.exists():
                user = getpass.getuser()
                with scripts.using_sudo():
                    scripts.chown(user, user, image_path)

    return ImageRules(build=build)


def _build(parameters, name, rules, image_path):
    scripts.run([
        parameters['//images/bases:builder'],
        *_make_verbose_args(),
        'build',
        *_make_builder_id_args(parameters),
        *('--base-version', parameters['//images/bases:base-version']),
        *_make_builder_image_args(parameters),
        *_make_image_data_args(parameters, name),
        *_make_rule_args(rules),
        _get_builder_name(name),
        parameters['//images/bases:version'],
        _get_builder_image_path(image_path),
    ])


def _merge(parameters, name, image_path):
    version = parameters['//images/bases:version']
    scripts.run([
        parameters['//images/bases:builder'],
        *_make_verbose_args(),
        'merge',
        *_make_builder_image_args(parameters),
        *('--image-nv', _get_builder_name(name), version),
        *_make_filter_args(parameters),
        name,
        version,
        image_path,
    ])


def _make_verbose_args():
    if shipyard2.is_debug():
        return ('--verbose', )
    else:
        return ()


def _make_builder_id_args(parameters):
    builder_id = parameters['//images/bases:builder-id']
    return () if builder_id is None else ('--builder-id', builder_id)


def _make_builder_image_args(parameters):
    for arg in parameters['//images/bases:builder-images']:
        if arg.startswith('id:'):
            yield '--image-id'
            yield arg[len('id:'):]
        elif arg.startswith('nv:'):
            _, name, version = arg.split(':', maxsplit=3)
            yield '--image-nv'
            yield name
            yield version
        elif arg.startswith('tag:'):
            yield '--image-tag'
            yield arg[len('tag:'):]
        else:
            ASSERT.unreachable('unknown builder image: {}', arg)


def _make_image_data_args(parameters, name):
    shipyard_data_path = parameters['//releases:shipyard-data']
    if shipyard_data_path is None:
        return ()
    image_data_path = shipyard_data_path / 'image-data'
    if not (image_data_path / foreman.get_relpath() / name).is_dir():
        return ()
    return ('--volume', '%s:/usr/src/image-data:ro' % image_data_path)


def _make_rule_args(rules):
    for rule in rules:
        yield '--rule'
        # We need a full label here; convert ':name' to '//path:name'.
        yield foreman.Label.parse(rule, implicit_path=foreman.get_relpath())


def _make_filter_args(parameters):
    for arg in parameters['//images/bases:filters']:
        if arg.startswith('include:'):
            yield '--include'
            yield arg[len('include:'):]
        elif arg.startswith('exclude:'):
            yield '--exclude'
            yield arg[len('exclude:'):]
        else:
            ASSERT.unreachable('unknown filter rule: {}', arg)
