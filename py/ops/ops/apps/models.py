"""\
Data model of a tightly-coupled container group, which is usually called
a "pod" (not to be confused with a Linux kernel cgroup).
"""

__all__ = [
    'ContainerGroupRepo',
]

import json
import logging
from pathlib import Path


LOG = logging.getLogger(__name__)


class ContainerGroupRepo:
    """The central repository of container groups.

       Directory structure:

         * ${CONFIGS}/pods/${NAME}/${VERSION}
           Directory for a pod's config files.

         * ${CONFIGS}/current/${NAME}
           Symlink to the currently deployed pod.

         * ${VOLUMES}/volumes/${NAME}/${VERSION}
           Directory for a pod's data volumes.
    """

    def __init__(self, config_path, data_path):
        config_path = Path(config_path).absolute()
        self._pods = config_path / 'pods'
        self._current = config_path / 'current'
        self._volumes = Path(data_path).absolute() / 'volumes'

    # Most methods should expect ContainerGroup object in their
    # arguments except these few methods below.

    def get_pod_names(self):
        try:
            return sorted(path.name for path in self._pods.iterdir())
        except FileNotFoundError:
            LOG.warning('cannot list directory: %s', self._pods)
            return []

    def iter_pods_from_name(self, pod_name):
        for version in self._iter_pod_versions(pod_name):
            yield self._get_pod(pod_name, version)

    def get_current_version_from_name(self, pod_name):
        """Return the version that is currently deployed."""
        link = self._get_current_path(pod_name)
        if not link.exists():
            # No version of this pod has been deployed.
            return None
        if not link.is_symlink():
            LOG.warning('not a symlink to pod: %s', link)
            return None
        return int(link.resolve().name)

    def find_pod(self, path_or_name):
        """Load a pod with either a path or a 'name:version' string."""
        if Path(path_or_name).exists():
            return ContainerGroup.load_json(path_or_name)
        else:
            pod_name, version = path_or_name.rsplit(':', 1)
            return self._get_pod(pod_name, version)

    # Below are "normal" methods that expect ContainerGroup object in
    # their arguments.

    def iter_pods(self, pod, exclude_self=False):
        """Iterate versions of a pod."""
        for version in self._iter_pod_versions(pod.name):
            if exclude_self and pod.version == version:
                continue
            yield self._get_pod(pod.name, version)

    def get_current_version(self, pod):
        return self.get_current_version_from_name(pod.name)

    def get_current_pod(self, pod):
        """Return the currently deployed pod."""
        version = self.get_current_version(pod)
        if version is None:
            return None
        else:
            return self._get_pod(pod.name, version)

    def get_current_path(self, pod):
        return self._get_current_path(pod.name)

    def get_config_path(self, pod):
        """Return the directory for this pod's config files."""
        return self._get_config_path(pod.name, pod.version)

    def get_volume_path(self, pod):
        return self._volumes / pod.name / str(pod.version)

    def _get_pod(self, pod_name, version):
        path = self._get_config_path(pod_name, version)
        return ContainerGroup.load_json(path)

    def _iter_pod_versions(self, pod_name):
        path = self._pods / pod_name
        try:
            versions = sorted(int(p.name) for p in path.iterdir())
        except FileNotFoundError:
            LOG.warning('cannot list directory: %s', path)
            versions = ()
        yield from versions

    def _get_current_path(self, pod_name):
        return self._current / pod_name

    def _get_config_path(self, pod_name, version):
        return self._pods / pod_name / str(version)


class ContainerGroup:

    POD_JSON = 'pod.json'

    PROP_NAMES = frozenset((
        'name',
        'version',
        'containers',
        'images',
        'volumes',
    ))

    @classmethod
    def load_json(cls, pod_path):
        pod_path = Path(pod_path)
        if pod_path.is_dir():
            pod_path = pod_path / cls.POD_JSON
        return cls(pod_path, json.loads(pod_path.read_text()))

    def __init__(self, pod_path, pod_data):
        ensure_names(self.PROP_NAMES, pod_data)

        # Path to this JSON file.
        self.path = pod_path.absolute()

        self.name = pod_data['name']
        self.version = int(pod_data['version'])

        self.containers = [
            Container(self, container_data)
            for container_data in pod_data.get('containers', ())
        ]

        self.images = [
            Image(self, image_data)
            for image_data in pod_data.get('images', ())
        ]

        self.volumes = [
            Volume(self, volume_data)
            for volume_data in pod_data.get('volumes', ())
        ]

    def __str__(self):
        return '%s:%s' % (self.name, self.version)


class Container:

    PROP_NAMES = frozenset(('name', 'replication', 'systemd'))

    def __init__(self, pod, container_data):
        ensure_names(self.PROP_NAMES, container_data)

        self.name = container_data['name']

        self.replication = container_data.get('replication', 1)
        if isinstance(self.replication, int):
            if self.replication < 1:
                raise ValueError('invalid replication: %d' % self.replication)

        systemd = container_data.get('systemd')
        self.systemd = Systemd(pod, self, systemd) if systemd else None

        # We only support systemd at the moment.
        if not self.systemd:
            raise ValueError('no process manager for container %s' % self.name)


class Systemd:

    PROP_NAMES = frozenset(('unit-files',))

    class Unit:

        # NOTE: We encode container group information into unit names,
        # and so they will not be the same as the unit _file_ names
        # specified in the pod.json (see also UNIT_NAME_FORMAT below).

        SYSTEM_PATH = Path('/etc/systemd/system')

        UNIT_NAME_FORMAT = \
            '{pod_name}-{container_name}:{pod_version}{templated}{suffix}'

        def __init__(self, pod, container, unit_file):

            # Path to the unit file (not to be confused with unit name
            # or the path to the unit file under /etc/systemd/system).
            self.path = pod.path.parent / unit_file

            self.is_templated = container.replication != 1

            # Name of this unit, which encodes the information of this
            # container group.
            self.name = self.UNIT_NAME_FORMAT.format(
                pod_name=pod.name,
                pod_version=pod.version,
                container_name=container.name,
                templated='@' if self.is_templated else '',
                suffix=self.path.suffix,
            )

            # If this unit is templated, this is a list of unit names of
            # the instances; otherwise it's an empty list.
            if self.is_templated:
                if isinstance(container.replication, int):
                    instances = range(container.replication)
                else:
                    instances = container.replication
                self.instances = [
                    self.UNIT_NAME_FORMAT.format(
                        pod_name=pod.name,
                        pod_version=pod.version,
                        container_name=container.name,
                        templated='@%s' % i,
                        suffix=self.path.suffix,
                    )
                    for i in instances
                ]
            else:
                self.instances = []

        @property
        def is_service(self):
            return self.name.endswith('.service')

        @property
        def system_path(self):
            """Path to the unit file under /etc/systemd/system."""
            return self.SYSTEM_PATH / self.name

        @property
        def dropin_path(self):
            path = self.system_path
            return path.with_name(path.name + '.d')

    def __init__(self, pod, container, systemd_data):
        ensure_names(self.PROP_NAMES, systemd_data)

        self.units = [
            Systemd.Unit(pod, container, unit_file)
            for unit_file in systemd_data.get('unit-files', ())
        ]

        # Unit names of services (precompute they for convenience).
        self.services = []
        for unit in self.units:
            if not unit.is_service:
                continue
            if unit.is_templated:
                self.services.extend(unit.instances)
            else:
                self.services.append(unit.name)


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

        signature = image_data.get('signature')
        self.signature = pod.path / signature if signature else None


class Volume:

    PROP_NAMES = frozenset(('name', 'path', 'read-only', 'data'))

    def __init__(self, pod, volume_data):
        ensure_names(self.PROP_NAMES, volume_data)

        self.name = volume_data['name']

        self.path = Path(volume_data['path'])

        self.read_only = bool(volume_data['read-only'])

        data = volume_data.get('data')
        self.data = pod.path.parent / data if data else None


def ensure_names(expect, actual):
    names = [name for name in actual if name not in expect]
    if names:
        raise ValueError('unknown names: %s' % ', '.join(names))
