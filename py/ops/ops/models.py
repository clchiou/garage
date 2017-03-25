"""Data model of pods."""

__all__ = [
    'Pod',
]

import collections
import copy
import logging
import re
import urllib.parse
from pathlib import Path


LOG = logging.getLogger(__name__)


# https://github.com/appc/spec/blob/master/spec/types.md#ac-name-type
AC_NAME_PATTERN = re.compile(r'[a-z0-9]+(-[a-z0-9]+)*')


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

    def __new__(cls, model_data, *_):
        errors = []
        for name, value in model_data.items():
            if name not in cls.FIELDS:
                errors.append('unknown field %r' % name)
                continue
            checks = cls.FIELDS[name]
            if not isinstance(checks, collections.Iterable):
                checks = [checks]
            for check in checks:
                error = check(name, value)
                if error:
                    errors.append(error)
        if errors:
            raise ValueError('incorrect model data: %s' % '; '.join(errors))
        return super().__new__(cls)

    def _path_or_uri(self, name, dir_path, path_or_uri):
        path_property = '%s_path' % name
        uri_property = '%s_uri' % name
        if not path_or_uri:
            setattr(self, path_property, None)
            setattr(self, uri_property, None)
        elif is_uri(path_or_uri):
            setattr(self, path_property, None)
            setattr(self, uri_property, path_or_uri)
        else:
            setattr(self, path_property, dir_path / path_or_uri)
            setattr(self, uri_property, None)

    def _warn_no_signature(self, name):
        uri = getattr(self, '%s_uri' % name)
        if uri and not (self.signature_path or self.signature_uri):
            LOG.warning('%s is from remote but no signature is provided: %s',
                        name, uri)


class Pod(ModelObject):

    FIELDS = {
        'name': (ModelObject.is_type_of(str), ModelObject.is_ac_name),
        'version': ModelObject.is_type_of(str, int),
        'systemd-units': ModelObject.is_type_of(list),
        'images': ModelObject.is_type_of(list),
        'volumes': ModelObject.is_type_of(list),
        'manifest': ModelObject.is_type_of(dict),
    }

    def __init__(self, pod_data, pod_path):
        """Create a pod object.

           pod_data: Data load from pod.json.
           pod_path: Path to the directory of the pod.
        """
        self.path = pod_path

        self.name = pod_data['name']
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

        self.manifest = pod_data['manifest']

    def __str__(self):
        return '%s:%s' % (self.name, self.version)

    def make_manifest(self, *,
                      # Provide deployment-time information
                      get_volume_path,
                      get_host_port):
        """Make Appc pod manifest."""

        # Make a copy before modifying it
        manifest = copy.deepcopy(self.manifest)

        # Insert volume source path
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
            if 'source' in appc_volume:
                raise ValueError('volume source was set: %s' % volume.name)
            appc_volume['source'] = str(get_volume_path(volume))

        # Collect port names from apps
        port_names = set()
        for app in manifest.get('apps', ()):
            for port in app.get('app', {}).get('ports', ()):
                port_names.add(port['name'])

        # Insert host ports
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


class SystemdUnit(ModelObject):
    """A SystemdUnit object has these properties:

       * unit_name
       * instances:
         If this unit is templated, it's an array of instantiated unit
         names, or else it is an empty array
       * unit_names:
         If this unit is templated, it's an alias to instances, or else
         it is an one element array of unit_name

       (Path under /etc/systemd/system)
       * unit_path
       * dropin_path

       (One of the two must be present)
       * unit_file_path: Path to the unit file
       * unit_file_uri: URI of the unit file

       * signature_path: Path to the unit file signature file
       * signature_uri: URI of the unit file signature file
    """

    FIELDS = {
        'unit-file': ModelObject.is_type_of(str),
        'signature': ModelObject.is_type_of(str),
        'instances': ModelObject.is_type_of(int, list),
    }

    UNITS_DIRECTORY = Path('/etc/systemd/system')

    # We encode pod information into unit name (and thus it will not be
    # the same as the name part of the unit file path in the pod.json)
    UNIT_NAME_FORMAT = '{name}-{stem}-{version}{templated}{suffix}'

    def __init__(self, unit_data, pod):

        self._path_or_uri('unit_file', pod.path, unit_data['unit-file'])
        self._path_or_uri('signature', pod.path, unit_data.get('signature'))
        self._warn_no_signature('unit_file')

        # Prepare for unit_name and instances
        if self.unit_file_uri:
            path = Path(urllib.parse.urlparse(self.unit_file_uri).path)
        else:
            path = self.unit_file_path
        stem = path.stem
        suffix = path.suffix

        instances = unit_data.get('instances', ())
        if isinstance(instances, int):
            if instances < 1:
                raise ValueError('invalid instances: %d' % instances)
            instances = range(instances)
        self.instances = tuple(
            self.UNIT_NAME_FORMAT.format(
                name=pod.name,
                version=pod.version,
                templated='@%s' % instance,
                stem=stem,
                suffix=suffix,
            )
            for instance in instances
        )

        templated = bool(self.instances)
        self.unit_name = self.UNIT_NAME_FORMAT.format(
            name=pod.name,
            version=pod.version,
            templated='@' if templated else '',
            stem=stem,
            suffix=suffix,
        )
        self.unit_names = self.instances if templated else (self.unit_name,)

        self.unit_path = self.UNITS_DIRECTORY / self.unit_name
        self.dropin_path = self.unit_path.with_name(self.unit_path.name + '.d')


class Image(ModelObject):

    FIELDS = {
        'id': ModelObject.is_type_of(str),
        'image': ModelObject.is_type_of(str),
        'signature': ModelObject.is_type_of(str),
    }

    def __init__(self, image_data, pod):

        self.id = image_data['id']

        self._path_or_uri('image', pod.path, image_data['image'])
        self._path_or_uri('signature', pod.path, image_data.get('signature'))
        self._warn_no_signature('image')


class Volume(ModelObject):

    FIELDS = {
        'name': (ModelObject.is_type_of(str), ModelObject.is_ac_name),
        'user': ModelObject.is_type_of(str),
        'group': ModelObject.is_type_of(str),
        'data': ModelObject.is_type_of(str),
        'signature': ModelObject.is_type_of(str),
    }

    def __init__(self, volume_data, pod):

        self.name = volume_data['name']

        self.user = volume_data.get('user', 'nobody')
        self.group = volume_data.get('group', 'nogroup')

        self._path_or_uri('data', pod.path, volume_data['data'])
        self._path_or_uri('signature', pod.path, volume_data.get('signature'))
        self._warn_no_signature('data')


# Only accept http and https at the moment
URI_SCHEME_PATTERN = re.compile(r'(\w+)://')
SUPPORTED_URI_SCHEMES = frozenset((
    'docker',
    'http',
    'https',
))


def is_uri(path_or_uri):
    match = URI_SCHEME_PATTERN.match(path_or_uri)
    if match:
        if match.group(1) not in SUPPORTED_URI_SCHEMES:
            raise ValueError('unsupported uri scheme: %s' % match.group(1))
        return True  # Assume it's URI
    else:
        return False
