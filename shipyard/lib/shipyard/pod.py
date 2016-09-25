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
    build_dict,
    build_appc_image,
    rsync,
    write_json,
)


Pod = partial(
    namedtuple('Pod', [
        'label_name',
        'pod_name',  # Default to label_name.
        'systemd_units',
        'make_manifest',
        'apps',
        'volumes',
        'depends',  # Dependencies for the build-pod rule.
        'files',
    ]),
    pod_name=None,
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
        'instances',
    ]),
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
        'label_name',
        'image_name',  # Default to label_name.
        'make_manifest',
        'depends',  # Dependencies for the build-image rule.
    ]),
    image_name=None,
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

    image_label = 'image/%s' % image.label_name
    (
        define_parameter(image_label)
        .with_default(image)
        .with_encode(lambda image: image._asdict())
    )

    rule = (
        define_rule('build-image/%s' % image.label_name)
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
        parameters['//base:output'] / image.label_name,
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
        'name': image.image_name or image.label_name,
    }
    if image.make_manifest:
        manifest = image.make_manifest(parameters, manifest)
    return manifest


def define_pod(pod):
    """Generate pod/POD parameter and build-pod/POD rules."""

    define_parameter('version/%s' % pod.label_name).with_type(int)

    pod_label = 'pod/%s' % pod.label_name
    define_parameter(pod_label).with_default(pod).with_encode(_encode_pod)

    rule = (
        define_rule('build-pod/%s' % pod.label_name)
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

    # Construct a list of unique `(id, label_name)` pairs.
    unique_images = set(
        (image_ids[app.image_label], parameters[app.image_label].label_name)
        for app in pod.apps
    )
    unique_images = sorted(unique_images)

    # Generate pod object for the ops scripts.
    pod_json_object = {
        'name': pod.pod_name or pod.label_name,
        'version': parameters['version/%s' % pod.label_name],
        'systemd-units': [
            (build_dict()
             .set('unit-file', to_path(unit.unit_file).name)
             .if_(unit.instances).set('instances', unit.instances).end_if()
             .dict)
            for unit in pod.systemd_units
        ],
        'images': [
            {
                'id': image_id,
                'path': '%s/image.aci' % label_name,
            }
            for image_id, label_name in unique_images
        ],
        'volumes': [
            (build_dict()
             .set('name', volume.name)
             .set('user', volume.user)
             .set('group', volume.group)
             .if_(volume.data).set('data', volume.data).end_if()
             .dict)
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
                    'name': (
                        parameters[app.image_label].image_name or
                        parameters[app.image_label].label_name
                    ),
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
    path = parameters['//base:output'] / image.label_name / 'sha512'
    return 'sha512-%s' % path.read_text().strip()
