"""\
Data model of a tightly-coupled container group, which is usually called
a "pod" (not to be confused with a Linux kernel cgroup).
"""

__all__ = [
    'ContainerGroup',
]

import json
import logging
from pathlib import Path


LOG = logging.getLogger(__name__)


class ContainerGroup:

    POD_JSON = 'pod.json'

    PROP_NAMES = frozenset(('name', 'version', 'containers', 'images'))

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

        self._root_config_path = None

    @property
    def root_config_path(self):
        if self._root_config_path is None:
            raise RuntimeError('ContainerGroup.root_config_path is not set')
        return self._root_config_path

    @root_config_path.setter
    def root_config_path(self, root_config_path):
        self._root_config_path = Path(root_config_path).absolute()

    @property
    def pod_config_path(self):
        return self.root_config_path / self.name

    @property
    def config_path(self):
        return self.pod_config_path / str(self.version)

    def get_pod(self, version):
        """Get pod for version."""
        path = self.root_config_path / self.name / str(version)
        pod = self.load_json(path)
        pod.root_config_path = self.root_config_path
        return pod

    def iter_pods(self):
        """Iterate pods of all versions."""
        for path in self.config_path.parent.iterdir():
            pod = self.load_json(path)
            pod.root_config_path = self.root_config_path
            yield pod


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
            # We need this mainly because `systemctl link` is not what
            # we expect it to be?
            return self.SYSTEM_PATH / self.name

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


def ensure_names(expect, actual):
    names = [name for name in actual if name not in expect]
    if names:
        raise ValueError('unknown names: %s' % ', '.join(names))
