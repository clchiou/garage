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
    """Generate build_image/IMAGE rule."""
    _define_image('build_image/%s' % image.name, image)


def _define_image(rule_name, image):
    rule = (
        define_rule(rule_name)
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
        parameters['//base:image'],
        parameters['//base:output'] / image.name,
    )


def define_pod(pod):
    """Generate build_pod/POD and build_pod/POD/IMAGE rules."""
    (
        define_parameter('version/%s' % pod.name)
        .with_type(int)
    )

    build_image_names = []
    for image in pod.images:
        build_image_name = 'build_pod/%s/%s' % (pod.name, image.name)
        build_image_names.append(build_image_name)
        _define_image(build_image_name, image)

    rule = (
        define_rule('build_pod/%s' % pod.name)
        .with_build(partial(_build_pod, pod=pod))
        .depend('//host/mako:install')
    )
    # TODO: We cannot build multiple images in one-pass at the moment.
    #for build_image_name in build_image_names:
    #    rule.depend(build_image_name)
    for depend in pod.depends:
        rule.depend(depend)


def _build_pod(parameters, pod):

    template_vars = {
        'name': pod.name,
        'version': parameters['version/%s' % pod.name],
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
