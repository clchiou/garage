"""Application images and pods build rule templates."""

__all__ = [
    'App',
    'Image',
    'Pod',
    'SystemdUnit',
    'Volume',
    'define_image',
    'define_pod',
    'derive_app_parameter',
]

from collections import OrderedDict, namedtuple
import functools
import hashlib
import json
import logging

from garage import scripts

from foreman import define_parameter, rule, to_path

from . import utils


LOG = logging.getLogger(__name__)


ImageRules = namedtuple('ImageRules', 'write_manifest build_image')


def define_image(image):
    """Define IMAGE_NAME/write_manifest and IMAGE_NAME/build_image rule.

       The image object will be stored at IMAGE_NAME parameter so that
       you may refer to them in other build files.

       The output will be written to OUTPUT/IMAGE_NAME directory.
    """

    (define_parameter(image.name)
     .with_doc('Spec data of image: %s' % image.name)
     .with_type(Image)
     .with_parse(Image.parse)
     .with_encode(Image.to_dict)
     .with_default(image))

    # TODO: Encrypt and/or sign the image

    @rule(image.name + '/write_manifest')
    @rule.depend('//base:tapeout')
    def write_manifest(parameters):
        """Create Appc image manifest file."""

        image.load(parameters)

        LOG.info('write appc image manifest: %s', image.name)
        utils.write_json_to(
            image.image_manifest,
            parameters['//base:drydock/manifest'],
        )

    @rule(image.name + '/build_image')
    @rule.depend('//base:tapeout')
    @rule.depend(image.name + '/write_manifest')
    @rule.annotate('rule-type', 'build_image')  # For do-build tool
    def build_image(parameters):
        """Build Appc container image."""

        image.load(parameters)

        output_dir = parameters['//base:output'] / image.name
        LOG.info('build appc image: %s', output_dir)

        image_data_dir = parameters['//base:drydock/build']
        scripts.ensure_file(image_data_dir / 'manifest')
        scripts.ensure_directory(image_data_dir / 'rootfs')

        scripts.mkdir(output_dir)
        image_path = output_dir / 'image.aci'
        if image_path.exists():
            LOG.warning('overwrite: %s', image_path)
        image_checksum_path = output_dir / 'sha512'

        scripts.pipeline(
            [
                lambda: scripts.tar_create(
                    image_data_dir, ['manifest', 'rootfs'],
                    tarball_path=None,
                    tar_extra_flags=['--numeric-owner'],
                ),
                lambda: _compute_sha512(image_checksum_path),
                lambda: scripts.gzip(speed=9),
            ],
            # Don't close file opened from image_path here because
            # pipeline() will close it
            pipe_output=image_path.open('wb'),
        )
        scripts.ensure_file(image_path)
        scripts.ensure_file(image_checksum_path)

    return ImageRules(
        write_manifest=write_manifest,
        build_image=build_image,
    )


def _compute_sha512(sha512_file_path):
    hasher = hashlib.sha512()
    pipe_input = scripts.get_stdin()
    pipe_output = scripts.get_stdout()
    while True:
        data = pipe_input.read(4096)
        if not data:
            break
        hasher.update(data)
        pipe_output.write(data)
    sha512_file_path.write_text('%s\n' % hasher.hexdigest())


PodRules = namedtuple('PodRules', 'build_pod')


def define_pod(pod):
    """Define POD_NAME/version parameter and POD_NAME/build_pod rule.

       The output will be written to OUTPUT directory (note that images
       are written to OUTPUT/IMAGE_NAME).
    """

    define_parameter.int_typed(pod.name + '/version')

    @rule(pod.name + '/build_pod')
    @rule.annotate('rule-type', 'build_pod')  # For do-build tool
    def build_pod(parameters):
        """Write out pod-related data files."""

        pod.load(parameters)

        # Construct the pod object and write it out to disk
        utils.write_json_to(
            pod.pod_object,
            parameters['//base:output'] / 'pod.json',
        )

        # Copy systemd unit files; it has to matches the "unit-file"
        # entry of unit.pod_object_entry
        if pod.systemd_units:
            scripts.rsync(
                [unit.path for unit in pod.systemd_units],
                parameters['//base:output'],
            )

    # HACK: Make build_pod rule "virtually" depend on build_image rules
    # so that build files are loaded, but build_image rules will not be
    # executed
    for image_label in pod.image_labels:
        build_pod.depend(image_label + '/build_image', when=lambda _: False)

    return PodRules(build_pod=build_pod)


def derive_app_parameter(name_or_func):
    """Define an App-typed parameter."""

    def decorator(name, func):
        return (define_parameter(name)
                .with_doc(func.__doc__)
                .with_type(App)
                .with_parse(App.parse)
                .with_encode(App.to_dict)
                .with_derive(func))

    if isinstance(name_or_func, str):
        return functools.partial(decorator, name=name_or_func)
    else:
        return decorator(name_or_func.__name__, name_or_func)


# Convention:
# pod_object_entry generates sub-entry of the pod object
# pod_manifest_entry_* generates sub-entry of the Appc pod manifest


class Pod:
    """Specify an application pod.

       NOTE: The elements of the `images` parameter may be an Image
       object or a label refer to an image parameter.
    """

    def __init__(self, name, *,
                 images=(),
                 systemd_units=()):
        self.name = name
        self.systemd_units = systemd_units
        self._volumes = None

        self._version = None

        images = list(images)
        if all(isinstance(image, Image) for image in images):
            self._images = images
            self._image_labels = [image.name for image in images]
            self._images_and_labels = None
        else:
            self._images = None
            self._image_labels = None
            self._images_and_labels = images

    def load(self, parameters):
        if self._version is None:
            self._version = parameters[self.name + '/version']

        if self._images is None:
            self._images = []
            self._image_labels = []
            for image_or_label in self._images_and_labels:
                if isinstance(image_or_label, Image):
                    self._images.append(image_or_label)
                    self._image_labels.append(image_or_label.name)
                else:
                    self._images.append(parameters[image_or_label])
                    self._image_labels.append(image_or_label)

        for image in self._images:
            image.load(parameters)

    @property
    def version(self):
        assert self._version is not None
        return self._version

    @property
    def images(self):
        assert self._images is not None
        return self._images

    @property
    def image_labels(self):
        assert self._image_labels is not None
        return self._image_labels

    @property
    def volumes(self):
        # Collect distinct volumes
        if self._volumes is None:
            volumes = {
                volume.name: volume
                for image in self.images
                for volume in image.app.volumes
            }
            self._volumes = sorted(volumes.values(), key=lambda v: v.name)
        return self._volumes

    @property
    def pod_object(self):
        """Construct the pod object for the ops tool."""
        return {
            'name': self.name,
            'version': self.version,
            'manifest': self.pod_manifest,
            'systemd-units': [
                unit.pod_object_entry
                for unit in self.systemd_units
            ],
            'images': [
                image.pod_object_entry
                for image in self.images
            ],
            'volumes': [
                volume.pod_object_entry
                for volume in self.volumes
            ],
        }

    @property
    def pod_manifest(self):
        return {
            'acVersion': '0.8.10',
            'acKind': 'PodManifest',
            'apps': [
                image.pod_manifest_entry
                for image in self.images
            ],
            'volumes': [
                volume.pod_manifest_entry_volume
                for volume in self.volumes
            ],
        }


class Image:
    """Specify an application image.

       NOTE: The `app` parameter may be an App object or a label refer
       to a parameter defining an App object.
    """

    @classmethod
    def parse(cls, data):
        if isinstance(data, str):
            data = json.loads(data)
        return cls(**data)

    @staticmethod
    def to_dict(image):
        return OrderedDict([
            ('id', image._id),
            ('name', image.name),
            ('app', image._app_label or App.to_dict(image._app)),
            ('read_only_rootfs', image.read_only_rootfs),
        ])

    def __init__(self, name, app, *,
                 read_only_rootfs=True):
        self._id = None
        self.name = name
        self.read_only_rootfs = read_only_rootfs
        if isinstance(app, App):
            self._app = app
            self._app_label = None
        else:
            self._app = None
            self._app_label = app

    def load(self, parameters):
        if self._id is None:
            path = parameters['//base:output'] / self.name / 'sha512'
            if path.is_file():
                self._id = 'sha512-%s' % path.read_text().strip()
        if self._app is None:
            self._app = parameters[self._app_label]

    @property
    def id(self):
        assert self._id is not None
        return self._id

    @property
    def app(self):
        assert self._app is not None
        return self._app

    @property
    def pod_object_entry(self):
        # image.aci is under OUTPUT/IMAGE_NAME
        return {
            'id': self.id,
            'path': '%s/image.aci' % self.name,
        }

    @property
    def pod_manifest_entry(self):
        """Return an app entry embedded in pod manifest."""
        entry = {
            'name': self.app.name,
            'image': {
                'name': self.name,
                'id': self.id,
            },
            'app': self.app.pod_manifest_entry,
            'readOnlyRootFS': self.read_only_rootfs,
        }
        return entry

    @property
    def image_manifest(self):
        """Return Appc image manifest."""
        return {
            'acKind': 'ImageManifest',
            'acVersion': '0.8.10',
            'name': self.name,
            'labels': [
                {
                    'name': 'arch',
                    'value': 'amd64',
                },
                {
                    'name': 'os',
                    'value': 'linux',
                },
            ],
            'app': self.app.pod_manifest_entry,
        }


class App:

    @classmethod
    def parse(cls, data):
        if isinstance(data, str):
            data = json.loads(data)
        return cls(**data)

    @staticmethod
    def to_dict(app):
        return OrderedDict([
            ('name', app.name),
            ('exec', app.exec),
            ('user', app.user),
            ('group', app.group),
            ('working_directory', app.working_directory),
            ('environment', OrderedDict(sorted(app.environment.items()))),
            ('volumes', list(map(Volume.to_dict, app.volumes))),
        ])

    def __init__(self, name, *,
                 exec=None,
                 user='nobody', group='nogroup',
                 working_directory='/',
                 environment=None,
                 volumes=()):
        self.name = name
        self.exec = exec or []
        self.user = user
        self.group = group
        self.working_directory = working_directory
        self.environment = environment or {}
        self.volumes = volumes or []

    @property
    def pod_manifest_entry(self):
        return {
            'exec': self.exec,
            'user': self.user,
            'group': self.group,
            'workingDirectory': self.working_directory,
            'environment': [
                {'name': name, 'value': self.environment[name]}
                for name in sorted(self.environment)
            ],
            'mountPoints': [
                volume.pod_manifest_entry_mount_point
                for volume in self.volumes
            ],
        }


class Volume:

    @staticmethod
    def to_dict(volume):
        return OrderedDict([
            ('name', volume.name),
            ('path', volume.path),
            ('user', volume.user),
            ('group', volume.group),
            ('data', volume.data),
            ('read_only', volume.read_only),
        ])

    def __init__(self, name, path, *,
                 user='nobody', group='nogroup',
                 data=None,
                 read_only=True):
        self.name = name
        self.path = path
        self.user = user
        self.group = group
        self.data = data
        self.read_only = read_only

    @property
    def pod_object_entry(self):
        entry = {
            'name': self.name,
            'user': self.user,
            'group': self.group,
        }
        if self.data:
            entry['data'] = self.data
        return entry

    @property
    def pod_manifest_entry_volume(self):
        return {
            # 'source' will be inserted by ops tool
            'name': self.name,
            'kind': 'host',
            'readOnly': self.read_only,
            'recursive': True,
        }

    @property
    def pod_manifest_entry_mount_point(self):
        return {
            'name': self.name,
            'path': self.path,
            'readOnly': self.read_only,
        }


class SystemdUnit:

    def __init__(self, unit_file, *, instances=None):
        self.unit_file = unit_file
        self.instances = instances

    @property
    def path(self):
        return to_path(self.unit_file)

    @property
    def pod_object_entry(self):
        # "unit-file" is relative path to OUTPUT; use path.name matches
        # the rsync() call above
        entry = {'unit-file': self.path.name}
        if self.instances:
            entry['instances'] = self.instances
        return entry
