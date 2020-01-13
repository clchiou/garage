"""Set up the base environment for image release processes."""

import contextlib
import logging
import tempfile
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2
from shipyard2.rules.images import utils

LOG = logging.getLogger(__name__)

# `build` is a do-nothing rule at the moment.
foreman.define_rule('build').depend('//releases:build')

(foreman.define_parameter('%s/version' % shipyard2.BASE)\
 .with_doc('base image version'))

(foreman.define_parameter.path_typed('%s/image' % shipyard2.BASE)\
 .with_doc('host path to base image output')
 .with_derive(utils.make_derive_image_path(shipyard2.BASE)))

(foreman.define_parameter.path_typed('%s/builder-image' % shipyard2.BASE)\
 .with_doc('host path to base builder image output')
 .with_derive(utils.make_derive_builder_image_path(shipyard2.BASE)))


@foreman.rule('%s/build' % shipyard2.BASE)
@foreman.rule.depend('//releases:build')
@foreman.rule.depend('build')
def base_build(parameters):
    version = ASSERT.not_none(parameters['%s/version' % shipyard2.BASE])
    image_paths = [
        parameters['%s/image' % shipyard2.BASE],
        parameters['%s/builder-image' % shipyard2.BASE],
    ]
    if all(map(Path.is_file, image_paths)):
        LOG.info('skip: build base: %s %s', version, image_paths)
        return
    ASSERT.not_any(image_paths, Path.is_file)
    LOG.info('build base: %s %s', version, image_paths)
    for image_path in image_paths:
        scripts.mkdir(image_path.parent)
    with contextlib.ExitStack() as stack:
        _build_base(stack, version, image_paths[0], image_paths[1])
    for image_path in image_paths:
        utils.chown(image_path)
    for image_path in image_paths:
        utils.ctr_import_image(image_path)


def _build_base(stack, version, base_path, base_builder_path):
    # Use base output directory for intermediate data.
    tempdir_path = stack.enter_context(
        tempfile.TemporaryDirectory(dir=base_path.parent)
    )
    LOG.info('generate base and base-builder under: %s', tempdir_path)
    base_builder_rootfs_path = Path(tempdir_path) / 'base-builder'
    stack.callback(utils.sudo_rm, base_builder_rootfs_path)
    utils.ctr([
        'images',
        'build-base',
        *('--prune-stash-path', base_builder_rootfs_path),
        shipyard2.BASE,
        version,
        base_path,
    ])
    utils.ctr_build_image(
        shipyard2.get_builder_name(shipyard2.BASE),
        version,
        base_builder_rootfs_path,
        base_builder_path,
    )
