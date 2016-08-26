"""Templates for building application pods."""

__all__ = [
    'Pod',
    'SystemdUnit',
    'App',
    'Image',
    'Volume',
    'define_image',
    'define_pod',
]

from collections import namedtuple
from functools import partial

from foreman import define_parameter, define_rule, to_path
from shipyard import (
    combine_dicts,
    build_appc_image,
    rsync,
    write_json,
)


Pod = partial(
    namedtuple('Pod', [
        'name',
        'systemd_units',
        'make_manifest',
        'apps',
        'images',
        'volumes',
        'depends',  # Dependencies for the build_pod rule.
        'files',
    ]),
    make_manifest=None,
    volumes=(),
    depends=(),
    files=(),
)


SystemdUnit = partial(
    namedtuple('SystemdUnit', [
        'unit_file',
        'start',
        'instances',
    ]),
    start=False,
    instances=None,
)


App = partial(
    namedtuple('App', [
        'name',
        'image_name',
        'volume_names',
        'read_only_rootfs',
    ]),
    volume_names=(),
    read_only_rootfs=False,
)


Image = partial(
    namedtuple('Image', [
        'name',
        'make_manifest',
        'depends',  # Dependencies for the build_image rule.
    ]),
    depends=(),
)


Volume = partial(
    namedtuple('Volume', [
        'name',
        'path',
        'user',
        'group',
        'data',
        'read_only',
    ]),
    user='nobody',
    group='nogroup',
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
    )
    for depend in image.depends:
        rule.depend(depend)


def _build_image(parameters, image):
    write_json(
        image.make_manifest(parameters, make_base_image_manifest(image)),
        parameters['//base:manifest'],
    )
    build_appc_image(
        parameters['//base:image'],
        parameters['//base:output'] / image.name,
    )


def make_base_image_manifest(image):
    return {
        'acKind': 'ImageManifest',
        'acVersion': '0.8.6',
        'labels': [
            {
                'name': 'os',
                'value': 'linux',
            },
            {
                'name': 'arch',
                'value': 'amd64',
            },
        ],
        'name': image.name,
    }


def define_pod(pod):
    """Generate build_pod/POD and build_pod/POD/IMAGE rules."""
    define_parameter('version/%s' % pod.name).with_type(int)

    for image in pod.images:
        _define_image('build_pod/%s/%s' % (pod.name, image.name), image)

    # Do not make build_pod/POD depend on build_pod/POD/IMAGE rules.
    # Our build system cannot build multiple images in one pass because
    # we use //base:tapeout as joint point.
    rule = (
        define_rule('build_pod/%s' % pod.name)
        .with_build(partial(_build_pod, pod=pod))
    )
    for depend in pod.depends:
        rule.depend(depend)


def _build_pod(parameters, pod):

    # Look-up tables.
    image_ids = {
        image.name: ('sha512-%s' %
                     ((parameters['//base:output'] / image.name / 'sha512')
                      .read_text()
                      .strip()))
        for image in pod.images
    }
    images = {image.name: image for image in pod.images}
    volumes = {volume.name: volume for volume in pod.volumes}

    def make_image_manifest(app):
        image_manifest = images[app.image_name].make_manifest(
            parameters,
            make_base_image_manifest(images[app.image_name]),
        )
        # Add 'mountPoints' to 'app' object.
        image_manifest['app'] = combine_dicts(
            image_manifest['app'],
            {
                'mountPoints': [
                    {
                        'volume': volume_name,
                        'path': volumes[volume_name].path,
                        'readOnly': volumes[volume_name].read_only,
                    }
                    for volume_name in app.volume_names
                ],
            },
        )
        return image_manifest

    pod_manifest = {
        'acVersion': '0.8.6',
        'acKind': 'PodManifest',
        'apps': [
            combine_dicts(
                # Embed 'app' object from image manifest.
                {
                    'app': make_image_manifest(app)['app'],
                },
                {
                    'name': app.name,
                    'image': {
                        'name': app.image_name,
                        'id': image_ids[app.image_name],
                    },
                    'readOnlyRootFS': app.read_only_rootfs,
                    'mounts': [
                        {
                            'volume': volume_name,
                            'path': volumes[volume_name].path,
                        }
                        for volume_name in app.volume_names
                    ],
                },
            )
            for app in pod.apps
        ],
        'volumes': [
            {
                'name': volume.name,
                'kind': 'host',
                # 'source' will be provided by ops scripts.
                'readOnly': volume.read_only,
                'recursive': True,
            }
            for volume in pod.volumes
        ],
    }
    if pod.make_manifest:
        pod_manifest = pod.make_manifest(parameters, pod_manifest)

    # Generate pod object for the ops scripts.
    pod_json_object = {
        'name': pod.name,
        'version': parameters['version/%s' % pod.name],
        'systemd-units': [
            combine_dicts(
                {
                    'unit-file': to_path(unit.unit_file).name,
                    'start': unit.start,
                },
                {
                    'instances': unit.instances,
                } if unit.instances else {},
            )
            for unit in pod.systemd_units
        ],
        'images': [
            {
                'id': image_ids[image.name],
                'path': '%s/image.aci' % image.name,
            }
            for image in pod.images
        ],
        'volumes': [
            combine_dicts(
                {
                    'name': volume.name,
                    'user': volume.user,
                    'group': volume.group,
                },
                {
                    'data': volume.data,
                } if volume.data else {},
            )
            for volume in pod.volumes
        ],
        'manifest': pod_manifest,
    }

    write_json(pod_json_object, parameters['//base:output'] / 'pod.json')

    rsync(
        [to_path(unit.unit_file) for unit in pod.systemd_units],
        parameters['//base:output'],
    )

    rsync(
        [to_path(label) for label in pod.files],
        parameters['//base:output'],
    )
