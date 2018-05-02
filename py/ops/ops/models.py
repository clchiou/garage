"""Data model of pods."""

__all__ = [
    'Pod',
]

import collections.abc
import copy
import logging
import os.path
import re
import urllib.parse
from pathlib import Path

from garage import scripts
from garage.assertions import ASSERT
from garage.collections import DictBuilder


LOG = logging.getLogger(__name__)


# https://github.com/appc/spec/blob/master/spec/types.md#ac-name-type
AC_NAME_PATTERN = re.compile(r'[a-z0-9]+(-[a-z0-9]+)*')


POD_NAME_PATTERN = '//{ac_name}(/{ac_name})*:{ac_name}'
POD_NAME_PATTERN = re.compile(
    POD_NAME_PATTERN.format(ac_name=AC_NAME_PATTERN.pattern))


# Layout inside a pod directory
POD_JSON = 'pod.json'
POD_MANIFEST_JSON = 'pod-manifest.json'
SYSTEMD = 'systemd'
IMAGES = 'images'
VOLUMES = 'volumes'
VOLUME_DATA = 'volume-data'


class PodName(str):
    """Format: `//pod/path:name`."""

    __slots__ = ('_colon_index',)

    def __new__(cls, name):
        ASSERT.true(name.startswith('//'))  # Just a sanity check.
        self = super().__new__(cls, name)
        self._colon_index = name.index(':')
        return self

    @property
    def path(self):
        return self[2:self._colon_index]

    @property
    def name(self):
        return self[self._colon_index+1:]

    def make_suitable_for_filename(self):
        """Make it suitable to be a part of file name.

        Note that theoretically it may lead to name conflicts but in
        practice this should not concern us, as double dash '--' is not
        commonly used "organically"; for example, all three of the pod
        names are transformed into the same unit name string:
          * //awesome/project:cool-stuff
          * //awesome--project:cool-stuff
          * //awesome:project--cool-stuff
        """
        return '%s--%s' % (self.path.replace('/', '--'), self.name)


class ModelObject:

    FIELDS = {}

    @staticmethod
    def is_type_of(*types):
        def check(name, value):
            if not isinstance(value, types):
                return 'wrong type for %r (%r)' % (name, type(value))
        return check

    @staticmethod
    def is_ac_name(property_name, name):
        if not AC_NAME_PATTERN.fullmatch(name):
            return 'invalid name for %r: %s' % (property_name, name)

    @staticmethod
    def is_pod_name(property_name, name):
        if not POD_NAME_PATTERN.fullmatch(name):
            return 'invalid pod name for %r: %s' % (property_name, name)

    def __new__(cls, model_data, *_):
        errors = []
        for name, value in model_data.items():
            if name not in cls.FIELDS:
                errors.append('unknown field %r' % name)
                continue
            checks = cls.FIELDS[name]
            if not isinstance(checks, collections.abc.Iterable):
                checks = [checks]
            for check in checks:
                error = check(name, value)
                if error:
                    errors.append(error)
        if errors:
            raise ValueError('incorrect model data: %s' % '; '.join(errors))
        return super().__new__(cls)

    def _path_or_uri(self, name, dir_path, path_or_uri, schemes):
        path_property = '%s_path' % name
        uri_property = '%s_uri' % name
        if not path_or_uri:
            setattr(self, path_property, None)
            setattr(self, uri_property, None)
        elif is_uri(path_or_uri, schemes):
            setattr(self, path_property, None)
            setattr(self, uri_property, path_or_uri)
        else:
            if Path(path_or_uri).is_absolute():
                raise ValueError('path is absolute: %s' % path_or_uri)
            setattr(self, path_property, dir_path / path_or_uri)
            setattr(self, uri_property, None)

    def _warn_if_uri_no_checksum(self, name):
        if getattr(self, name + '_uri') and not self.checksum:
            LOG.warning('uri is not accompanied by checksum: %s', name)

    def _suffix(self, name):
        if getattr(self, name + '_path'):
            path = getattr(self, name + '_path')
        elif getattr(self, name + '_uri'):
            uri = getattr(self, name + '_uri')
            path = Path(urllib.parse.urlparse(uri).path)
        else:
            raise AssertionError
        return ''.join(path.suffixes)


class Pod(ModelObject):

    FIELDS = {
        'name': (ModelObject.is_type_of(str), ModelObject.is_pod_name),
        'version': ModelObject.is_type_of(str, int),
        'systemd-units': ModelObject.is_type_of(list),
        'images': ModelObject.is_type_of(list),
        'volumes': ModelObject.is_type_of(list),
        'ports': ModelObject.is_type_of(list),
        'manifest': ModelObject.is_type_of(dict),
    }

    def __init__(self, pod_data, pod_path):
        """Create a pod object.

        pod_data: Data loaded from pod.json.
        pod_path: Path to the directory of the pod.
        """
        self.path = pod_path

        self.name = PodName(pod_data['name'])
        self.version = str(pod_data['version'])

        self.systemd_units = tuple(
            SystemdUnit(data, self)
            for data in pod_data.get('systemd-units', ()))
        if not self.systemd_units:
            LOG.warning('no systemd units for pod: %s', self)

        self.images = tuple(
            Image(data, self) for data in pod_data.get('images', ()))
        self.volumes = tuple(
            Volume(data, self) for data in pod_data.get('volumes', ()))
        self.ports = tuple(
            Port(data) for data in pod_data.get('ports', ()))

        self.manifest = pod_data['manifest']

    def __str__(self):
        return '%s@%s' % (self.name, self.version)

    def to_pod_data(self):
        """Do a "reverse" of __init__.

        This returns a shallow copy - be careful if you modify it!
        """
        return {
            'name': self.name,
            'version': self.version,
            'systemd-units': list(
                map(SystemdUnit.to_pod_data, self.systemd_units)),
            'images': list(map(Image.to_pod_data, self.images)),
            'volumes': list(map(Volume.to_pod_data, self.volumes)),
            'ports': list(map(Port.to_pod_data, self.ports)),
            'manifest': self.manifest,
        }

    def morph_into_local_pod(self, pod_path):
        """Change paths under the assumption that this pod is entirely
        stored locally in a pod directory (all URI properties will be
        unset).
        """
        self.path = pod_path
        for unit in self.systemd_units:
            unit.morph_into_local_pod(pod_path)
        for image in self.images:
            image.morph_into_local_pod(pod_path)
        for volume in self.volumes:
            volume.morph_into_local_pod(pod_path)

    def make_local_pod(self, pod_path):
        """Make another pod object at a local directory, assuming that
        all URIs "do not exist".

        This is useful if this pod object is loaded from a deploy
        bundle, and we are copying everything the a pod directory.
        """
        pod = Pod(self.to_pod_data(), pod_path)
        pod.morph_into_local_pod(pod.path)
        return pod

    def make_manifest(
            self, *,
            # Provide deployment-time information.
            get_volume_path, get_host_port):
        """Make Appc pod manifest."""

        # Make a copy before modifying it.
        manifest = copy.deepcopy(self.manifest)

        # Insert volume source path.
        appc_volumes = {
            appc_volume['name']: appc_volume
            for appc_volume in manifest.get('volumes', ())
        }
        for volume in self.volumes:
            appc_volume = appc_volumes.get(volume.name)
            if appc_volume is None:
                raise ValueError('no pod volume: %s' % volume.name)
            if appc_volume['kind'] != 'host':
                raise ValueError('non-host volume: %s' % volume.name)
            if 'source' not in appc_volume:
                appc_volume['source'] = str(get_volume_path(volume))

        # Collect port names from apps.
        port_names = set()
        for app in manifest.get('apps', ()):
            for port in app.get('app', {}).get('ports', ()):
                port_names.add(port['name'])

        # Insert host ports.
        if port_names:
            ports = manifest.setdefault('ports', [])
            defined_port_names = frozenset(port['name'] for port in ports)
            for port_name in sorted(port_names):
                if port_name in defined_port_names:
                    LOG.debug('skip already-defined port: %s', port_name)
                    continue
                ports.append({
                    'name': port_name,
                    'hostPort': int(get_host_port(port_name)),
                })

        return manifest

    @property
    def pod_object_path(self):
        return self.path / POD_JSON

    @property
    def pod_manifest_path(self):
        return self.path / POD_MANIFEST_JSON

    @property
    def pod_manifests_path(self):
        return self.path / 'pod-manifests'

    def get_pod_manifest_path(self, instance):
        return self.pod_manifests_path / (instance.unit_name + '.json')

    @property
    def pod_systemd_path(self):
        return self.path / SYSTEMD

    @property
    def pod_images_path(self):
        return self.path / IMAGES

    @property
    def pod_volumes_path(self):
        return self.path / VOLUMES

    @property
    def pod_volume_data_path(self):
        return self.path / VOLUME_DATA

    def iter_instances(self):
        for unit in self.systemd_units:
            for instance in unit.instances:
                yield instance

    def filter_instances(self, predicate):
        return filter(predicate, self.iter_instances())

    @staticmethod
    def should_but_not_enabled(instance):
        """Return True when an instance should be but is not enabled."""
        return (
            instance.enable and
            not scripts.systemctl_is_enabled(instance.unit_name)
        )

    @staticmethod
    def should_but_not_started(instance):
        """Return True when an instance should be but is not started."""
        return (
            instance.start and
            not scripts.systemctl_is_active(instance.unit_name)
        )

    def is_enabled(self, *, predicate=None):
        predicate = predicate or self.should_but_not_enabled
        enabled = True
        for instance in self.filter_instances(predicate):
            LOG.debug('unit is not enabled: %s', instance.unit_name)
            enabled = False
        return enabled

    def is_started(self, *, predicate=None):
        predicate = predicate or self.should_but_not_started
        started = True
        for instance in self.filter_instances(predicate):
            LOG.debug('unit is not started: %s', instance.unit_name)
            started = False
        return started


class SystemdUnit(ModelObject):
    """A SystemdUnit object has these properties:

    * unit_name: Base part of unit_path; if this unit is templated, this
      is the template unit name (e.g., foo@.service).
    * unit_path
    * instances: If this unit is templated, it is a list of instantiated
      units; else it is a list of just the unit itself.

    An instance object has:
      * unit_name: Base part of unit_path; if this unit is templated,
        this is the instantiated unit name (e.g., foo@bar.service).
      * Path under /etc/systemd/system:
        * unit_path
        * dropin_path

    Source of the unit file; one of the two must be present:
    * unit_file_path: Path to the unit file in the bundle.
    * unit_file_uri: URI of the unit file to fetch from.
    """

    FIELDS = {
        'name': ModelObject.is_type_of(str),
        'unit-file': ModelObject.is_type_of(str),
        'enable': ModelObject.is_type_of(bool, list),
        'start': ModelObject.is_type_of(bool, list),
        'checksum': ModelObject.is_type_of(str),
        'instances': ModelObject.is_type_of(int, list),
    }

    SUPPORTED_URI_SCHEMES = frozenset((
        'http',
        'https',
    ))

    UNITS_DIRECTORY = Path('/etc/systemd/system')

    # We encode pod information into unit name (and thus it will not be
    # the same as the name part of the unit file path in the pod.json)
    UNIT_NAME_FORMAT = '{pod_name}--{stem}--{version}{templated}{suffix}'

    class Instance:

        # Although we could match the escape sequence and specifier with
        # some regex ninjutsu, we choose not of that, but a less fancy
        # approach.
        _INSTANCE_NAME_PATTERN = re.compile(r'%+i')

        def __init__(self, *, name, unit_name, enable, start):
            self.name = name
            self.unit_name = unit_name
            self.dropin_path = SystemdUnit.UNITS_DIRECTORY / (unit_name + '.d')
            self.enable = enable
            self.start = start

        def resolve_specifier(self, contents):
            """Resolve %i with instance name."""
            if self.name is None:
                # Do not resolve since this is not templated.
                return contents
            positions = []
            for match in self._INSTANCE_NAME_PATTERN.finditer(contents):
                begin, end = match.span()
                if (end - begin) % 2 == 0:
                    positions.append(end - 2)
            pieces = []
            name = str(self.name)
            begin = 0
            for end in positions:
                if begin < end:
                    pieces.append(contents[begin:end])
                pieces.append(name)
                begin = end + 2
            pieces.append(contents[begin:])
            return ''.join(pieces)

    def __init__(self, unit_data, pod):

        self._unit_file = unit_data['unit-file']
        self._path_or_uri('unit_file', pod.path, self._unit_file,
                          self.SUPPORTED_URI_SCHEMES)
        self.enable = unit_data.get('enable', True)
        self.start = unit_data.get('start', True)
        self.checksum = unit_data.get('checksum')
        self._warn_if_uri_no_checksum('unit_file')

        # Prepare for unit_name and instances
        if self.unit_file_uri:
            path = Path(urllib.parse.urlparse(self.unit_file_uri).path)
        else:
            path = self.unit_file_path

        # Strip '@' in case you add one to the end.
        self.name = unit_data.get('name', path.stem).rstrip('@')

        # Keep a copy in self._instance for to_pod_data().
        self._instances = unit_data.get('instances', ())

        if isinstance(self._instances, int):
            ASSERT.greater_or_equal(self._instances, 1)
            instance_names = range(self._instances)
        else:
            instance_names = self._instances

        pod_unit_name = pod.name.make_suitable_for_filename()

        is_templated = bool(instance_names)

        self.unit_name = self.UNIT_NAME_FORMAT.format(
            pod_name=pod_unit_name,
            stem=self.name,
            version=pod.version,
            templated='@' if is_templated else '',
            suffix=path.suffix,
        )
        self.unit_path = self.UNITS_DIRECTORY / self.unit_name

        if is_templated:
            if isinstance(self.enable, bool):
                enable = [self.enable] * len(instance_names)
            else:
                enable = self.enable
            ASSERT.equal(len(enable), len(instance_names))
            if isinstance(self.start, bool):
                start = [self.start] * len(instance_names)
            else:
                start = self.start
            ASSERT.equal(len(start), len(instance_names))
        else:
            enable = ASSERT.type_of(self.enable, bool)
            start = ASSERT.type_of(self.start, bool)

        if is_templated:
            self.instances = [
                self.Instance(
                    name=name,
                    unit_name=self.UNIT_NAME_FORMAT.format(
                        pod_name=pod_unit_name,
                        stem=self.name,
                        version=pod.version,
                        templated='@%s' % name,
                        suffix=path.suffix,
                    ),
                    enable=enable[i],
                    start=start[i],
                )
                for i, name in enumerate(instance_names)
            ]
        else:
            self.instances = [
                self.Instance(
                    name=None,
                    unit_name=self.unit_name,
                    enable=enable,
                    start=start,
                )
            ]

    def to_pod_data(self):
        return (
            DictBuilder()
            .setitem('name', self.name)
            .setitem('unit-file', self._unit_file)
            .setitem('enable', self.enable)
            .setitem('start', self.start)
            .if_(self.checksum).setitem('checksum', self.checksum).end()
            .if_(self._instances).setitem('instances', self._instances).end()
            .dict
        )

    def morph_into_local_pod(self, pod_path):
        self._unit_file = os.path.join(SYSTEMD, self.unit_name)
        self.unit_file_path = pod_path / self._unit_file
        self.unit_file_uri = None

    def is_installed(self):
        """Return True when unit is installed.

        NOTE: Our term "installed", which merely means that unit files
        are copied to the right places, is the same as "loaded", which
        means systemd has parsed these unit files.
        """
        # TODO: Replace is_installed with is_loaded.
        return (
            self.unit_path.exists() and
            all(instance.dropin_path.exists() for instance in self.instances)
        )


class Image(ModelObject):

    FIELDS = {
        'id': ModelObject.is_type_of(str),
        'image': ModelObject.is_type_of(str),
        'signature': ModelObject.is_type_of(str),
    }

    SUPPORTED_URI_SCHEMES = frozenset((
        'docker',
        'http',
        'https',
    ))

    def __init__(self, image_data, pod):
        self.id = image_data['id']
        self._image = image_data['image']
        self._path_or_uri('image', pod.path, self._image,
                          self.SUPPORTED_URI_SCHEMES)
        self._signature = image_data.get('signature')
        self.signature = (
            pod.path / self._signature if self._signature else None)

    def to_pod_data(self):
        return (
            DictBuilder()
            .setitem('id', self.id)
            .setitem('image', self._image)
            .if_(self._signature).setitem('signature', self._signature).end()
            .dict
        )

    def morph_into_local_pod(self, pod_path):
        # Assume first 16 characters of sha512 is sufficient to avoid
        # name conflicts.
        new_name = self.id[:(7+16)]
        if self.image_path:
            self._image = os.path.join(
                IMAGES, new_name + self._suffix('image'))
            self.image_path = pod_path / self._image
        else:
            ASSERT.true(self.image_uri)
        if self.signature:
            self._signature = os.path.join(
                IMAGES, new_name + ''.join(self.signature.suffixes))
            self.signature = pod_path / self._signature


class Volume(ModelObject):

    FIELDS = {
        'name': (ModelObject.is_type_of(str), ModelObject.is_ac_name),
        'user': ModelObject.is_type_of(str),
        'group': ModelObject.is_type_of(str),
        'data': ModelObject.is_type_of(str),
        'checksum': ModelObject.is_type_of(str),
    }

    SUPPORTED_URI_SCHEMES = frozenset((
        'http',
        'https',
    ))

    def __init__(self, volume_data, pod):

        self.name = volume_data['name']

        self.user = volume_data.get('user', 'nobody')
        self.group = volume_data.get('group', 'nogroup')

        self._data = volume_data.get('data')
        self._path_or_uri('data', pod.path, self._data,
                          self.SUPPORTED_URI_SCHEMES)
        self.checksum = volume_data.get('checksum')
        self._warn_if_uri_no_checksum('data')

    def to_pod_data(self):
        return (
            DictBuilder()
            .setitem('name', self.name)
            .if_(self.user != 'nobody').setitem('user', self.user).end()
            .if_(self.group != 'nogroup').setitem('group', self.group).end()
            .if_(self._data).setitem('data', self._data).end()
            .if_(self.checksum).setitem('checksum', self.checksum).end()
            .dict
        )

    def morph_into_local_pod(self, pod_path):
        if self._data:
            self._data = os.path.join(
                VOLUME_DATA, self.name + self._suffix('data'))
            self.data_path = pod_path / self._data
            self.data_uri = None


class Port(ModelObject):

    FIELDS = {
        'name': (ModelObject.is_type_of(str), ModelObject.is_ac_name),
        'host-ports': ModelObject.is_type_of(list),
    }

    def __init__(self, port_data):
        self.name = port_data['name']
        self.host_ports = port_data['host-ports']

    def to_pod_data(self):
        return {
            'name': self.name,
            'host-ports': list(self.host_ports),
        }


URI_SCHEME_PATTERN = re.compile(r'(\w+)://')


def is_uri(path_or_uri, uri_schemes):
    match = URI_SCHEME_PATTERN.match(path_or_uri)
    if match:
        if match.group(1) not in uri_schemes:
            raise ValueError('unsupported uri scheme: %s' % match.group(1))
        return True  # Assume it's a URI.
    else:
        return False
