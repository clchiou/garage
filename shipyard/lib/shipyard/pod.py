"""Templates for building application pods."""

__all__ = [
    'Pod',
    'Image',
    'Volume',
    'define_image',
    'define_pod',
]

from collections import namedtuple
from functools import partial
from pathlib import Path

from foreman import define_parameter, define_rule, to_path
from shipyard import (
    build_appc_image,
    render_appc_manifest,
    render_files,
    rsync,
)


Pod = partial(
    namedtuple('Pod', [
        'name',
        'template_files',
        'make_template_vars',
        'files',
        'images',
        'volumes',
        'depends',  # Dependencies for the build_pod rule.
    ]),
    template_files=(),
    make_template_vars=lambda parameters: None,
    files=(),
    volumes=(),
    depends=(),
)


Image = partial(
    namedtuple('Image', [
        'name',
        'manifest',
        'make_template_vars',
        'depends',  # Dependencies for the build_image rule.
    ]),
    make_template_vars=lambda parameters: None,
    depends=(),
)


Volume = partial(
    namedtuple('Volume', [
        'name',
        'path',
        'data',
        'read_only',
    ]),
    data=None,
    read_only=True,
)


def define_image(image):
    """Generate build_image/IMAGE_NAME rule."""
    rule = (
        define_rule('build_image/%s' % image.name)
        .with_build(partial(_build_image, image=image))
        .depend('//base:tapeout')
        .depend('//host/mako:install')
    )
    for depend in image.depends:
        rule.depend(depend)


def _build_image(parameters, image):
    template_vars = {
        'name': image.name,
    }
    template_vars.update(image.make_template_vars(parameters) or {})
    render_appc_manifest(parameters, image.manifest, template_vars)
    build_appc_image(
        parameters['//base:build_out'],
        parameters['//base:output'] / image.name,
    )


def define_pod(pod):
    (
        define_parameter('version')
        .with_doc("""Pod version.""")
        .with_type(int)
    )
    for image in pod.images:
        define_image(image)
    # Define build rules for the application pod.
    # NOTE: build_pod should not depend not the build_image rules.
    rule = (
        define_rule('build_pod/%s' % pod.name)
        .with_build(partial(_build_pod, pod=pod))
        .depend('//host/mako:install')
    )
    for depend in pod.depends:
        rule.depend(depend)


def _build_pod(parameters, pod):

    template_vars = {
        'name': pod.name,
        'version': parameters['version'],
        'images': {
            image.name: {
                'sha512': ((parameters['//base:output'] /
                            image.name / 'sha512')
                           .read_text()
                           .strip()),
                'path': '%s/image.aci' % image.name,
            }
            for image in pod.images
        },
        'volumes': [volume._asdict() for volume in pod.volumes],
    }
    template_vars.update(pod.make_template_vars(parameters) or {})

    render_files(
        parameters,
        label_path_pairs=[
            (label, parameters['//base:output'] / Path(label).name)
            for label in pod.template_files
        ],
        template_vars=template_vars,
    )

    rsync(
        [to_path(label) for label in pod.files],
        parameters['//base:output'],
    )
