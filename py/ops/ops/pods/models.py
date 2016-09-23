"""Data model of pods."""

__all__ = [
    'Pod',
]

import copy
import json
import logging
import re
import urllib.parse
from pathlib import Path


LOG = logging.getLogger(__name__)


# https://github.com/appc/spec/blob/master/spec/types.md#ac-name-type
AC_NAME_PATTERN = re.compile(r'[a-z0-9]+(-[a-z0-9]+)*')


class Pod:

    # ${POD_DIR}/...
    POD_JSON = 'pod.json'
    POD_MANIFEST_JSON = 'pod-manifest.json'

    # ${POD_DIR}/units/${UNIT_FILE}
    UNITS_DIR = 'units'

    # ${POD_DIR}/volumes/${VOLUME}
    VOLUMES_DIR = 'volumes'

    PROP_NAMES = frozenset((
        'name',
        'version',
        'systemd-units',
        'images',
        'volumes',
        'manifest',
    ))

    @classmethod
    def load_json(cls, pod_path):
        pod_path = Path(pod_path)
        if pod_path.is_dir():
            pod_path = pod_path / cls.POD_JSON
        pod_data = json.loads(pod_path.read_text())
        return cls(pod_path, pod_data)

    def __init__(self, pod_path, pod_data):
        ensure_names(self.PROP_NAMES, pod_data)

        # Path to this JSON file.
        self.path = pod_path.absolute()

        self.name = pod_data['name']
        if not AC_NAME_PATTERN.fullmatch(self.name):
            raise ValueError('invalid pod name: %s' % self.name)
        self.version = int(pod_data['version'])

        self.systemd_units = tuple(
            SystemdUnit(self, unit_data)
            for unit_data in pod_data.get('systemd-units', ())
        )
        if not self.systemd_units:
            LOG.warning('no systemd units for pod %s', self)

        self.images = tuple(
            Image(self, image_data)
            for image_data in pod_data.get('images', ())
        )

        self.volumes = tuple(
            Volume(self, volume_data)
            for volume_data in pod_data.get('volumes', ())
        )

        self.manifest = pod_data['manifest']

    def make_manifest(
            self, *,
            # Providers of deployment-time information.
            get_volume_path,
            get_host_port):

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
            if 'source' in appc_volume:
                raise ValueError('volume source was set: %s' % volume.name)
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

    def __str__(self):
        return '%s:%s' % (self.name, self.version)


class SystemdUnit:

    PROP_NAMES = frozenset((
        'unit-file',
        'instances',
    ))

    # NOTE: We encode pod information into unit names, and so they will
    # not be the same as the unit _file_ names specified in the pod.json
    # (see also UNIT_NAME_FORMAT below).

    SYSTEM_PATH = Path('/etc/systemd/system')

    UNIT_NAME_FORMAT = '{pod_name}-{stem}-{pod_version}{templated}{suffix}'

    def __init__(self, pod, unit_data):
        ensure_names(self.PROP_NAMES, unit_data)

        # self.path to the unit file (not to be confused with unit name
        # or the path to the unit file under /etc/systemd/system).
        unit_file = unit_data['unit-file']
        if is_uri(unit_file):
            self.path = None
            self.uri = unit_file
        else:
            self.path = pod.path.parent / unit_file
            self.uri = None

        if self.uri:
            path = Path(urllib.parse.urlparse(self.uri).path)
            stem = path.stem
            suffix = path.suffix
        else:
            assert self.path
            stem = self.path.stem
            suffix = self.path.suffix

        # If this unit is templated, this is a list of unit names of the
        # instances; otherwise it's an empty list.
        if 'instances' in unit_data:
            instances = unit_data.get('instances', 1)
            if isinstance(instances, int):
                if instances < 1:
                    raise ValueError('invalid instances: %d' % instances)
                instances = range(instances)
            elif not instances:
                raise ValueError('empty instances: %r' % instances)
            self.instances = tuple(
                self.UNIT_NAME_FORMAT.format(
                    pod_name=pod.name,
                    pod_version=pod.version,
                    templated='@%s' % instance,
                    stem=stem,
                    suffix=suffix,
                )
                for instance in instances
            )
            assert self.instances
        else:
            self.instances = ()

        # Name of this unit, which encodes the information of this pod.
        self.name = self.UNIT_NAME_FORMAT.format(
            pod_name=pod.name,
            pod_version=pod.version,
            templated='@' if self.instances else '',
            stem=stem,
            suffix=suffix,
        )

    @property
    def unit_path(self):
        """Path to the unit file under /etc/systemd/system."""
        return self.SYSTEM_PATH / self.name

    @property
    def dropin_path(self):
        return self.unit_path.with_name(self.unit_path.name + '.d')

    @property
    def unit_names(self):
        if self.instances:
            return self.instances
        else:
            return (self.name,)


class Image:

    PROP_NAMES = frozenset(('id', 'path', 'uri', 'signature'))

    def __init__(self, pod, image_data):
        ensure_names(self.PROP_NAMES, image_data)

        self.id = image_data['id']

        path = image_data.get('path')
        self.path = pod.path.parent / path if path else None

        self.uri = image_data.get('uri')

        if self.path and self.uri:
            raise ValueError('both "path" and "uri" are set')
        if not self.path and not self.uri:
            raise ValueError('none of "path" and "uri" are set')

        signature = image_data.get('signature')
        if signature is None:
            self.signature = None
        elif is_uri(signature):
            if not self.uri:
                raise ValueError('"signature" is URI but "uri" is not set')
            self.signature = signature
        else:
            if not self.path:
                raise ValueError('"signature" is path but "path" is not set')
            self.signature = pod.path.parent / signature


class Volume:

    PROP_NAMES = frozenset((
        'name',
        'user',
        'group',
        'data',
    ))

    def __init__(self, pod, volume_data):
        ensure_names(self.PROP_NAMES, volume_data)

        self.name = volume_data['name']
        if not AC_NAME_PATTERN.fullmatch(self.name):
            raise ValueError('invalid volume name: %s' % self.name)

        self.user = volume_data.get('user', 'nobody')
        self.group = volume_data.get('group', 'nogroup')

        data = volume_data.get('data')
        if data is None:
            self.path = None
            self.uri = None
        elif is_uri(data):
            self.path = None
            self.uri = data
        else:
            self.path = pod.path.parent / data
            self.uri = None


def ensure_names(expect, actual):
    names = [name for name in actual if name not in expect]
    if names:
        raise ValueError('unknown names: %s' % ', '.join(names))


URI_SCHEME_PATTERN = re.compile(r'(\w+)://')
SUPPORTED_URI_SCHEMES = frozenset((
    'http',
    'https',
))


def is_uri(path_or_uri):
    match = URI_SCHEME_PATTERN.match(path_or_uri)
    if match:
        if match.group(1) not in SUPPORTED_URI_SCHEMES:
            raise ValueError('unsupported URI scheme: %s' % match.group(1))
        return True  # Assume it's URI.
    else:
        return False
