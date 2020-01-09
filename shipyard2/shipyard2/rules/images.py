"""Helpers for writing rules under //images."""

__all__ = [
    'bootstrap',
    'define_image',
    'get_image_path',
]

import dataclasses
import getpass
import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2
import shipyard2.rules

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class ImageRules:
    build: foreman.Rule
    merge: foreman.Rule


# NOTE: This function is generally called in the host system, not inside
# a builder pod.
def get_image_path(parameters, label, version):
    # We require absolute label for now.
    label = foreman.Label.parse(label)
    return (
        parameters['//releases:root'] / \
        shipyard2.RELEASE_IMAGES_DIR_NAME /
        label.path /
        label.name /
        version /
        shipyard2.IMAGE_DIR_IMAGE_FILENAME
    )


def _get_image_path(parameters, name, version):
    return (
        parameters['//releases:root'] / \
        foreman.get_relpath() /
        name /
        version /
        shipyard2.IMAGE_DIR_IMAGE_FILENAME
    )


def _get_builder_name(name):
    return name + '-builder'


def _get_builder_image_path(parameters, name, version):
    return (
        parameters['//releases:root'] / \
        foreman.get_relpath() /
        name /
        version /
        shipyard2.IMAGE_DIR_BUILDER_IMAGE_FILENAME
    )


def bootstrap(parameters):
    version = ASSERT.equal(
        parameters['//images/bases:base-version'],
        parameters['//images/bases:version'],
    )
    image_paths = [
        _get_image_path(parameters, shipyard2.BASE, version),
        _get_builder_image_path(parameters, shipyard2.BUILDER_BASE, version),
    ]
    if all(map(Path.is_file, image_paths)):
        LOG.info('skip: bootstrap: %s', version)
        return
    ASSERT.not_any(image_paths, Path.is_file)
    LOG.info('bootstrap: %s', version)
    for image_path in image_paths:
        scripts.mkdir(image_path.parent)
    scripts.run([
        parameters['//images/bases:builder'],
        *_make_verbose_args(),
        'bootstrap',
        *('--base-version', version),
        *image_paths,
    ])
    for image_path in image_paths:
        _chown(image_path)


def define_image(
    name,
    rules,
):
    """Define an application image.

    This defines:
    * Rule: name/build.
    * Rule: name/merge.

    NOTE: These rules are generally run in the host system, not inside a
    builder pod.
    """
    ASSERT.not_empty(rules)
    name_prefix = shipyard2.rules.canonicalize_name_prefix(name)
    rule_build = name_prefix + 'build'
    rule_merge = name_prefix + 'merge'

    @foreman.rule(rule_build)
    @foreman.rule.depend('//images/bases:build')
    @foreman.rule.depend('//releases:build')
    def build(parameters):
        version = parameters['//images/bases:version']
        output = _get_builder_image_path(parameters, name, version)
        if output.exists():
            LOG.info('skip: build image: %s %s', name, version)
            return
        LOG.info('build image: %s %s', name, version)
        scripts.mkdir(output.parent)
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
            version,
            output,
        ])
        _chown(output)

    @foreman.rule(rule_merge)
    @foreman.rule.depend('//images/bases:build')
    @foreman.rule.depend('//releases:build')
    @foreman.rule.depend(rule_build)
    def merge(parameters):
        version = parameters['//images/bases:version']
        output = _get_image_path(parameters, name, version)
        if output.exists():
            LOG.info('skip: merge image: %s %s', name, version)
            return
        LOG.info('merge image: %s %s', name, version)
        scripts.mkdir(output.parent)
        scripts.run([
            parameters['//images/bases:builder'],
            *_make_verbose_args(),
            'merge',
            *_make_builder_image_args(parameters),
            *('--image-nv', _get_builder_name(name), version),
            *_make_filter_args(parameters),
            name,
            version,
            output,
        ])
        _chown(output)

    return ImageRules(build=build, merge=merge)


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
    return ('--mount', '%s:/usr/src/image-data:ro' % image_data_path)


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


def _chown(path):
    user = getpass.getuser()
    with scripts.using_sudo():
        scripts.chown(user, user, path)
