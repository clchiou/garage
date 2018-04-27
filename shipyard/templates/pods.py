"""Build rule template for and object model of images and pods."""

__all__ = [
    # Pod object model.
    'App',
    'Image',
    'Pod',
    'Port',
    'SystemdUnit',
    'Volume',
    # Volume object model.
    'FileSpec',
    'VolumeSpec',
    # Build rule template as decorator.
    'app_specifier',
    'image_specifier',
    'volume_specifier',
    'pod_specifier',
]

from collections import OrderedDict, namedtuple
import hashlib
import json
import logging
import re
import tarfile

from garage import scripts

from foreman import define_parameter, define_rule, rule, to_path

from . import filespecs as filespecs_lib
from . import utils
from .volumes import apply_filespec_to_tarball


LOG = logging.getLogger(__name__)


### Build rule template


#
# We want the best of both worlds for application pod metadata:
#
# * Rules may declare dependencies, which is the only way to instruct
#   foreman to load more build files, but rules are only executed at
#   build time.
#
# * Parameters may not declare dependencies (not technically impossible,
#   but this feature is somehow not implemented), but parameters can be
#   evaluated anytime.
#
# These application pod metadata are parameters, which means we may
# evaluate them anytime (this makes scripting easier because scripts
# that parse metadata do not have to execute builds beforehand).
#
# In addition, we provide do-nothing "specify" rules for the purpose of
# declaring parameter dependencies; if a parameter is defined in another
# build file, you simply declare a dependency between the specify rules,
# and foreman will load that build file.
#
# There is one more advantage of do-nothing specify rules: It makes
# build_pod rules do not directly depend on build_image rules; and so
# you (or build scripts) may build pods and images separately.
#


AppRules = namedtuple('AppRules', 'specify_app')


def app_specifier(specifier):
    """Define NAME/specify_app rule."""

    name = specifier.__name__ + '/'

    App.define_parameter(specifier.__name__).with_derive(specifier)

    specify_app = (
        define_rule(name + 'specify_app')
        .depend('//base:build')
        .with_annotation('rule-type', 'specify_app')  # For release tool.
        .with_annotation('app-parameter', specifier.__name__)
    )

    return AppRules(specify_app=specify_app)


ImageRules = namedtuple(
    'ImageRules', 'specify_image write_manifest build_image')


def image_specifier(specifier):
    """Define these rules.

    The rules include:
    * NAME/specify_image
    * NAME/write_manifest
    * NAME/build_image

    The output will be written to OUTPUT/IMAGE_NAME directory.
    """

    # TODO: Encrypt and/or sign the image

    name = specifier.__name__ + '/'

    Image.define_parameter(specifier.__name__).with_derive(specifier)

    define_parameter(name + 'version')

    specify_image = (
        define_rule(name + 'specify_image')
        .depend('//base:build')
        .with_annotation('rule-type', 'specify_image')  # For release tool.
        .with_annotation('build-image-rule', name + 'build_image')
    )

    @rule(name + 'write_manifest')
    @rule.depend('//base:tapeout')
    @rule.depend(name + 'specify_image')
    def write_manifest(parameters):
        """Create Appc image manifest file."""
        LOG.info('write appc image manifest: %s', specifier.__name__)
        image = parameters[specifier.__name__]
        image._version = parameters[name + 'version']
        utils.write_json_to(
            image.get_image_manifest(),
            parameters['//base:drydock/manifest'],
        )

    @rule(name + 'build_image')
    @rule.depend(name + 'specify_image')  # For release tool.
    @rule.depend(name + 'write_manifest')
    @rule.annotate('rule-type', 'build_image')  # For release tool.
    @rule.annotate('image-parameter', specifier.__name__)
    @rule.annotate('version-parameter', name + 'version')
    def build_image(parameters):
        """Build Appc container image."""

        image = parameters[specifier.__name__]

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

        def tar_create():
            # Use sudo in case there are non-readable files.
            with scripts.using_sudo():
                scripts.tar_create(
                    image_data_dir, ['manifest', 'rootfs'],
                    tarball_path=None,
                    tar_extra_flags=['--numeric-owner'],
                )

        scripts.pipeline(
            [
                tar_create,
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
        specify_image=specify_image,
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


VolumeRules = namedtuple('VolumeRules', 'specify_volume build_volume')


def volume_specifier(specifier):
    """Define NAME/build_volume rule.

    The output will be written to OUTPUT/VOLUME_NAME directory.
    """

    name = specifier.__name__ + '/'

    VolumeSpec.define_parameter(specifier.__name__).with_derive(specifier)

    define_parameter(name + 'version')

    specify_volume = (
        define_rule(name + 'specify_volume')
        .depend('//base:build')
        .with_annotation('rule-type', 'specify_volume')  # For release tool.
        .with_annotation('build-volume-rule', name + 'build_volume')
    )

    @rule(name + 'build_volume')
    @rule.depend(name + 'specify_volume')
    @rule.annotate('rule-type', 'build_volume')  # For release tool.
    @rule.annotate('volume-parameter', specifier.__name__)
    @rule.annotate('version-parameter', name + 'version')
    def build_volume(parameters):
        """Build volume tarball."""
        volumespec = parameters[specifier.__name__]
        tarball_path = (
            parameters['//base:output'] / volumespec.tarball_filename)
        # XXX `open` of Python 3.5 doesn't accept path-like.
        with tarfile.open(str(tarball_path), 'x:gz') as tarball:
            for filespec in volumespec.filespecs:
                apply_filespec_to_tarball(filespec, tarball)

    return VolumeRules(
        specify_volume=specify_volume,
        build_volume=build_volume,
    )


PodRules = namedtuple('PodRules', 'specify_pod build_pod')


def pod_specifier(specifier):
    """Define NAME/build_pod rule.

    The output will be written to OUTPUT directory (note that images are
    written to OUTPUT/IMAGE_NAME).
    """

    name = specifier.__name__ + '/'

    Pod.define_parameter(specifier.__name__).with_derive(specifier)

    define_parameter(name + 'version')

    specify_pod = (
        define_rule(name + 'specify_pod')
        .depend('//base:build')
        .with_annotation('rule-type', 'specify_pod')  # For release tool.
    )

    @rule(name + 'build_pod')
    @rule.depend(name + 'specify_pod')
    @rule.annotate('rule-type', 'build_pod')  # For release tool.
    @rule.annotate('pod-parameter', specifier.__name__)
    @rule.annotate('version-parameter', name + 'version')
    def build_pod(parameters):
        """Write out pod-related data files."""

        pod = parameters[specifier.__name__]
        pod._version = parameters[name + 'version']
        for image in pod.images:
            image.load_id(parameters)

        # Construct the pod object and write it out to disk.
        utils.write_json_to(
            pod.get_pod_object(),
            parameters['//base:output'] / 'pod.json',
        )

        # Copy systemd unit files; it has to matches the "unit-file"
        # entry of unit.get_pod_object_entry().
        if pod.systemd_units:
            scripts.rsync(
                [unit.path for unit in pod.systemd_units],
                parameters['//base:output'],
            )

    return PodRules(specify_pod=specify_pod, build_pod=build_pod)


### Object model


# https://github.com/appc/spec/blob/master/spec/types.md
AC_IDENTIFIER_PATTERN = re.compile(r'[a-z0-9]+([-._~/][a-z0-9]+)*')
AC_NAME_PATTERN = re.compile(r'[a-z0-9]+(-[a-z0-9]+)*')


POD_NAME_PATTERN = '//{ac_name}(/{ac_name})*:{ac_name}'
POD_NAME_PATTERN = re.compile(
    POD_NAME_PATTERN.format(ac_name=AC_NAME_PATTERN.pattern))


# Convention:
# get_pod_object_entry generates sub-entry of the pod object
# get_pod_manifest_entry_* generates sub-entry of the Appc pod manifest


class ModelObject:

    # TODO: Use the new annotation syntax after we upgrade to Python 3.6
    FIELDS = []

    @classmethod
    def define_parameter(cls, name):
        return (
            define_parameter(name)
            .with_type(cls)
            .with_parse(cls.from_dict)
            .with_encode(cls.to_dict)
        )

    @classmethod
    def from_dict(cls, data):
        if isinstance(data, str):
            data = json.loads(data)
        else:
            data = dict(data)  # Make a copy before modifying
        for name, annotation in cls.FIELDS:
            if name not in data:
                pass
            elif isinstance(annotation, list) and len(annotation) == 1:
                element_type = annotation[0]
                data[name] = list(map(element_type.from_dict, data[name]))
            elif (isinstance(annotation, type) and
                  issubclass(annotation, ModelObject)):
                data[name] = annotation.from_dict(data[name])
        return cls(**data)

    @classmethod
    def to_dict(cls, obj):
        data = OrderedDict()
        for name, annotation in cls.FIELDS:
            if annotation is None:
                data[name] = getattr(obj, name)
            elif (isinstance(annotation, type) and
                  issubclass(annotation, ModelObject)):
                data[name] = annotation.to_dict(getattr(obj, name))
            elif isinstance(annotation, list) and len(annotation) == 1:
                element_type = annotation[0]
                elements = getattr(obj, name)
                data[name] = list(map(element_type.to_dict, elements))
            else:
                raise AssertionError
        return data

    @staticmethod
    def _ensure_ac_identifier(name):
        if name is not None and not AC_IDENTIFIER_PATTERN.fullmatch(name):
            raise ValueError('not valid AC identifier: %s' % name)
        return name

    @staticmethod
    def _ensure_ac_name(name):
        if name is not None and not AC_NAME_PATTERN.fullmatch(name):
            raise ValueError('not valid AC name: %s' % name)
        return name

    @staticmethod
    def _ensure_pod_name(name):
        if name is not None and not POD_NAME_PATTERN.fullmatch(name):
            raise ValueError('not valid pod name: %s' % name)
        return name


class Environment(ModelObject):

    @staticmethod
    def from_dict(data):
        return data

    @staticmethod
    def to_dict(obj):
        return OrderedDict(sorted(obj.items()))


class Volume(ModelObject):

    # TODO: Accept URI as well as path
    # TODO: Accept checksum, or calculate it from path

    FIELDS = [
        ('name', None),
        ('path', None),
        ('user', None),
        ('group', None),
        ('data', None),
        ('host_path', None),
        ('read_only', None),
    ]

    def __init__(
            self, *,
            name,
            path,
            user='nobody', group='nogroup',
            data=None,
            host_path=None,
            read_only=True):
        if data and host_path:
            raise ValueError(
                'both data and host_path are set: %r, %r' %
                (data, host_path)
            )
        self.name = self._ensure_ac_name(name)
        self.path = path
        self.user = user
        self.group = group
        self.data = data
        self.host_path = host_path
        self.read_only = read_only

    def get_pod_object_entry(self):
        entry = {
            'name': self.name,
            'user': self.user,
            'group': self.group,
        }
        if self.data:
            entry['data'] = self.data
        return entry

    def get_pod_manifest_entry_volume(self):
        entry = {
            # 'source' may be inserted by ops tool.
            'name': self.name,
            'kind': 'host',
            'readOnly': self.read_only,
            'recursive': True,
        }
        if self.host_path:
            entry['source'] = self.host_path
        return entry

    def get_pod_manifest_entry_mount_point(self):
        return {
            'name': self.name,
            'path': self.path,
            'readOnly': self.read_only,
        }


class Port(ModelObject):

    FIELDS = [
        ('name', None),
        ('protocol', None),
        ('port', None),
        ('host_port', None),
        ('host_ports', None),
    ]

    def __init__(
            self, *,
            name,
            protocol,
            port,
            host_port=None, host_ports=()):
        self.name = self._ensure_ac_name(name)
        if protocol not in ('tcp', 'udp'):
            raise ValueError('unsupported protocol: %s' % protocol)
        self.protocol = protocol
        self.port = port
        if host_port is not None and host_ports:
            raise ValueError(
                'both host_port and host_ports are set: %r, %r' %
                (host_port, host_ports),
            )
        self.host_port = host_port
        self.host_ports = host_ports

    def get_pod_object_entry(self):
        if not self.host_ports:
            raise AssertionError('no host ports')
        return {
            'name': self.name,
            'host-ports': list(self.host_ports),
        }

    def get_pod_manifest_entry_port(self):
        """Return declared port (for app entry)."""
        return {
            'name': self.name,
            'port': self.port,
            'protocol': self.protocol,
        }

    def get_pod_manifest_entry_exposed_port(self):
        """Return exposed port (for pod entry)."""
        if self.host_port is None:
            raise AssertionError('no host port')
        return {
            'name': self.name,
            'hostPort': self.host_port,
        }


class App(ModelObject):

    FIELDS = [
        ('name', None),
        ('exec', None),
        ('user', None),
        ('group', None),
        ('working_directory', None),
        ('environment', Environment),
        ('volumes', [Volume]),
        ('ports', [Port]),
        ('extra_app_entry_fields', None),
    ]

    def __init__(
            self, *,
            name,
            exec=None,
            user='nobody', group='nogroup',
            working_directory='/',
            environment=None,
            volumes=(),
            ports=(),
            extra_app_entry_fields=None):
        self.name = self._ensure_ac_name(name)
        self.exec = exec or []
        self.user = user
        self.group = group
        self.working_directory = working_directory
        self.environment = environment or {}
        self.volumes = volumes or []
        self.ports = ports or []
        self.extra_app_entry_fields = extra_app_entry_fields or {}

    def get_pod_manifest_entry(self):
        # Make a copy first (it's a shallow copy though).
        entry = dict(self.extra_app_entry_fields)
        entry.update({
            'exec': self.exec,
            'user': self.user,
            'group': self.group,
            'workingDirectory': self.working_directory,
            'environment': [
                {'name': name, 'value': self.environment[name]}
                for name in sorted(self.environment)
            ],
            'mountPoints': [
                volume.get_pod_manifest_entry_mount_point()
                for volume in self.volumes
            ],
            'ports': [
                port.get_pod_manifest_entry_port()
                for port in self.ports
            ],
        })
        return entry


class Image(ModelObject):

    # TODO: Accept docker://... URI.

    #
    # We need special treatment for should-be-writable directories, like
    # /tmp, when rootfs is mounted as read-only, but at the moment rkt
    # does not support tmpfs (https://github.com/rkt/rkt/issues/3547).
    #
    # We could work around this issue in either shipyard or ops-onboard
    # tool.  It looks like it makes more sense to do it here; so here we
    # go.
    #

    FIELDS = [
        ('id', None),
        ('name', None),
        ('version', None),
        ('app', App),
        ('read_only_rootfs', None),
        # When read_only_rootfs is True, these are directories that
        # should be made writable.
        ('writable_directories', None),
    ]

    def __init__(
            self, *,
            id=None,
            name,
            version=None,
            app,
            read_only_rootfs=True, writable_directories=('/tmp',)):
        self._id = id
        self.name = self._ensure_ac_identifier(name)
        self._version = version
        self.app = app
        self.read_only_rootfs = read_only_rootfs
        self.writable_directories = writable_directories

    def load_id(self, parameters):
        if self._id is None:
            path = parameters['//base:output'] / self.name / 'sha512'
            self._id = 'sha512-%s' % path.read_text().strip()

    @property
    def id(self):
        if self._id is None:
            LOG.warning('image has no id: %s', self.name)
        return self._id

    @property
    def version(self):
        if self._version is None:
            LOG.warning('image has no version: %s', self.name)
        return self._version

    def get_pod_object_entry(self):
        # image.aci is under OUTPUT/IMAGE_NAME.
        # TODO: Generate "signature" field.
        return {
            'id': self.id,
            'image': '%s/image.aci' % self.name,
        }

    def get_generated_mount_point_name(self, path):
        """Generate mount point name (for writable directory).

        Path `/foo/bar` will be named "image-name--foo-bar"; this should
        avoid most potential name conflicts; if there still are, the
        caller should raise an error.
        """
        return '%s--%s' % (self.name, '-'.join(filter(None, path.split('/'))))

    def get_pod_manifest_entry(self):
        """Return an app entry embedded in pod manifest."""

        app = self.app.get_pod_manifest_entry()

        # Add writable directory mount points.
        if self.read_only_rootfs and self.writable_directories:

            mount_points = app['mountPoints']

            mount_point_names = frozenset(mp['name'] for mp in mount_points)

            for path in self.writable_directories:
                name = self.get_generated_mount_point_name(path)
                if name in mount_point_names:
                    raise ValueError(
                        'mount point name conflict: %r in %r' %
                        (name, mount_point_names)
                    )
                mount_points.append({
                    'name': name,
                    'path': path,
                    'readOnly': False,
                })

        entry = {
            'name': self.app.name,
            'image': {
                'name': self.name,
                'id': self.id,
            },
            'app': app,
            'readOnlyRootFS': self.read_only_rootfs,
        }

        return entry

    def get_image_manifest(self):
        """Return Appc image manifest."""

        labels = [
            {
                'name': 'arch',
                'value': 'amd64',
            },
            {
                'name': 'os',
                'value': 'linux',
            },
        ]

        version = self.version
        if version is not None:
            labels.append({
                'name': 'version',
                'value': version,
            })

        return {
            'acKind': 'ImageManifest',
            'acVersion': '0.8.10',
            'name': self.name,
            'labels': labels,
            'app': self.app.get_pod_manifest_entry(),
        }


class FileSpec(filespecs_lib.FileSpec, ModelObject):

    FIELDS = [(field, None) for field in filespecs_lib.FileSpec._fields]

    def __new__(cls, **spec_data):
        spec_data = filespecs_lib.populate_filespec(spec_data)
        return super().__new__(cls, **spec_data)


class VolumeSpec(ModelObject):

    FIELDS = [
        ('name', None),
        ('tarball_filename', None),
        ('filespecs', [FileSpec]),
    ]

    def __init__(self, *, name, tarball_filename, filespecs):
        self.name = name
        self.tarball_filename = tarball_filename
        self.filespecs = filespecs


class SystemdUnit(ModelObject):

    # TODO: Accept URI for unit_file
    # TODO: Accept checksum, or calculate it from unit_file

    FIELDS = [
        ('unit_file', None),
        ('enable', None),
        ('start', None),
        ('instances', None),
    ]

    def __init__(self, *, unit_file, enable=True, start=True, instances=None):
        self.unit_file = unit_file
        self.enable = enable
        self.start = start
        self.instances = instances

    @property
    def path(self):
        return to_path(self.unit_file)

    def get_pod_object_entry(self):
        # "unit-file" is relative path to OUTPUT; use path.name matches
        # the rsync() call above
        entry = {
            'unit-file': self.path.name,
            'enable': self.enable,
            'start': self.start,
        }
        if self.instances:
            entry['instances'] = self.instances
        return entry


class Pod(ModelObject):

    FIELDS = [
        # NOTE: Unlike other names, pod name is not an AC name and has
        # format '//pod/path:name'.
        ('name', None),
        ('version', None),
        ('images', [Image]),
        ('systemd_units', [SystemdUnit]),
        ('volume_mapping', None),
    ]

    def __init__(
            self, *,
            name, version=None,
            images=None,
            systemd_units=None,
            volume_mapping=None):
        self.name = self._ensure_pod_name(name)
        self._version = version
        self.images = images or []
        self.systemd_units = systemd_units or []
        self.volume_mapping = volume_mapping or []
        self._volumes = None

    @property
    def version(self):
        if self._version is None:
            LOG.warning('pod has no version: %s', self.name)
        return self._version

    @property
    def volumes(self):
        # Collect distinct volumes.
        if self._volumes is None:
            volumes = {
                volume.name: volume
                for image in self.images
                for volume in image.app.volumes
            }
            self._volumes = sorted(volumes.values(), key=lambda v: v.name)
        return self._volumes

    def get_pod_object(self):
        """Construct the pod object for the ops tool."""

        entry = {
            'name': self.name,
            'manifest': self.get_pod_manifest(),
            'systemd-units': [
                unit.get_pod_object_entry()
                for unit in self.systemd_units
            ],
            'images': [
                image.get_pod_object_entry()
                for image in self.images
            ],
            'volumes': [
                volume.get_pod_object_entry()
                for volume in self.volumes
                # NOTE: We do not need to allocate stateful volumes if
                # host paths are assigned to them, because in this case,
                # container runtime can handle this volume all by itself
                # (i.e., we only need to keep a volume record in pod
                # manifest below, not here).
                if not volume.host_path
            ],
            'ports': [
                port.get_pod_object_entry()
                for image in self.images
                for port in image.app.ports
                if port.host_ports
            ],
        }

        version = self.version
        if version is not None:
            entry['version'] = version

        return entry

    def get_pod_manifest(self):

        volumes = [
            volume.get_pod_manifest_entry_volume()
            for volume in self.volumes
        ]

        generated_mount_point_names = set()
        for image in self.images:
            if image.read_only_rootfs and image.writable_directories:
                for path in image.writable_directories:
                    name = image.get_generated_mount_point_name(path)
                    if name in generated_mount_point_names:
                        raise ValueError(
                            'mount point name conflict: %r in %r' %
                            (name, generated_mount_point_names)
                        )
                    volumes.append({
                        'name': name,
                        'kind': 'empty',
                        'readOnly': False,
                        'recursive': True,
                        # Althouth we specify the sticky, unfortunately
                        # rkt doesn't support it.
                        'mode': '1777',
                    })

        return {
            'acVersion': '0.8.10',
            'acKind': 'PodManifest',
            'apps': [
                image.get_pod_manifest_entry()
                for image in self.images
            ],
            'volumes': volumes,
            'ports': [
                port.get_pod_manifest_entry_exposed_port()
                for image in self.images
                for port in image.app.ports
                if port.host_port
            ],
        }
