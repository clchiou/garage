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
        'volumes',
        'depends',  # Dependencies for the build-pod rule.
        'files',
    ]),
    systemd_units=(),
    make_manifest=None,
    apps=(),
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
        'image_label',
        'make_app_object',
        'volume_names',
        'read_only_rootfs',
    ]),
    make_app_object=None,
    volume_names=(),
    read_only_rootfs=False,
)


Image = partial(
    namedtuple('Image', [
        'name',
        'make_manifest',
        'depends',  # Dependencies for the build-image rule.
    ]),
    make_manifest=None,
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
    """Generate image/IMAGE parameter and build-image/IMAGE rule."""

    image_label = 'image/%s' % image.name
    (
        define_parameter(image_label)
        .with_default(image)
        .with_encode(lambda image: image._asdict())
    )

    rule = (
        define_rule('build-image/%s' % image.name)
        .with_build(partial(_build_image, image_label=image_label))
        .depend('//base:tapeout')
    )
    for depend in image.depends:
        rule.depend(depend)


def _build_image(parameters, *, image_label):
    image = parameters[image_label]
    write_json(
        _make_image_manifest(parameters, image),
        parameters['//base:manifest'],
    )
    build_appc_image(
        parameters['//base:image'],
        parameters['//base:output'] / image.name,
    )


def _make_image_manifest(parameters, image):
    manifest = {
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
    if image.make_manifest:
        manifest = image.make_manifest(parameters, manifest)
    return manifest


def define_pod(pod):
    """Generate pod/POD parameter and build-pod/POD rules."""

    define_parameter('version/%s' % pod.name).with_type(int)

    pod_label = 'pod/%s' % pod.name
    define_parameter(pod_label).with_default(pod).with_encode(_encode_pod)

    rule = (
        define_rule('build-pod/%s' % pod.name)
        .with_build(partial(_build_pod, pod_label=pod_label))
    )
    for depend in pod.depends:
        rule.depend(depend)
    # HACK: Make build-pod rule "virtually" depend on build-image rules
    # so that build files are loaded, but build-image rules will not be
    # executed.
    for app in pod.apps:
        rule.depend(
            app.image_label.replace('image/', 'build-image/', 1),
            when=lambda _: False,
        )


# For nicer-looking output.
def _encode_pod(pod):
    return (
        pod
        ._replace(
            systemd_units=[unit._asdict() for unit in pod.systemd_units],
            apps=[app._asdict() for app in pod.apps],
            volumes=[volume._asdict() for volume in pod.volumes],
        )
        ._asdict()
    )


def _build_pod(parameters, *, pod_label):

    pod = parameters[pod_label]

    image_ids = {
        app.image_label: _read_id(parameters, parameters[app.image_label])
        for app in pod.apps
    }

    # Construct a list of unique `(id, name)` pairs.
    unique_images = set(
        (image_ids[app.image_label], parameters[app.image_label].name)
        for app in pod.apps
    )
    unique_images = sorted(unique_images)

    # Generate pod object for the ops scripts.
    pod_json_object = {
        'name': pod.name,
        'version': parameters['version/%s' % pod.name],
        'systemd-units': [
            combine_dicts(
                {'unit-file': to_path(unit.unit_file).name},
                {'start': True} if unit.start else {},
                {'instances': unit.instances} if unit.instances else {},
            )
            for unit in pod.systemd_units
        ],
        'images': [
            {
                'id': image_id,
                'path': '%s/image.aci' % image_name,
            }
            for image_id, image_name in unique_images
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
        'manifest': _make_pod_manifest(parameters, pod, image_ids),
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


def _make_pod_manifest(parameters, pod, image_ids):

    volumes = {
        volume.name: volume
        for volume in pod.volumes
    }

    manifest = {
        'acVersion': '0.8.6',
        'acKind': 'PodManifest',
        'apps': [
            {
                'name': app.name,
                'image': {
                    'name': parameters[app.image_label].name,
                    'id': image_ids[app.image_label],
                },
                'app': _make_app_object(parameters, app, volumes),
                'readOnlyRootFS': app.read_only_rootfs,
                'mounts': [
                    {
                        'volume': volume_name,
                        'path': volumes[volume_name].path,
                    }
                    for volume_name in app.volume_names
                ],
            }
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
        manifest = pod.make_manifest(parameters, manifest)

    return manifest


def _make_app_object(parameters, app, volumes):
    manifest = _make_image_manifest(parameters, parameters[app.image_label])
    app_object = manifest['app']
    app_object.setdefault('mountPoints', []).extend(
        {
            'volume': volume_name,
            'path': volumes[volume_name].path,
            'readOnly': volumes[volume_name].read_only,
        }
        for volume_name in app.volume_names
    )
    if app.make_app_object:
        app_object = app.make_app_object(parameters, app_object)
    return app_object


def _read_id(parameters, image):
    path = parameters['//base:output'] / image.name / 'sha512'
    return 'sha512-%s' % path.read_text().strip()
