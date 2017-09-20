"""Pod repository."""

__all__ = [
    'PodState',
    'Ports',
    'Repo',
]

from collections import namedtuple
import enum
import json
import logging

from garage import scripts

from ops import models


# This is the version of the file layout
VERSION = 1


LOG = logging.getLogger(__name__)


class PodState(enum.Enum):
    """
    Pods go through this state transition:

        +---deploy---+  +--start--+
        |            v  |         v
      UNDEPLOYED   DEPLOYED     STARTED
        ^            |  ^         |
        +--undeploy--+  +--stop---+
    """
    UNDEPLOYED = 'undeployed'
    DEPLOYED = 'deployed'
    STARTED = 'started'


class Repo:

    @staticmethod
    def get_repo_dir(root_dir):
        return root_dir.absolute() / ('v%d' % VERSION)

    @classmethod
    def get_lock_path(cls, root_dir):
        return cls.get_repo_dir(root_dir) / 'lock'

    def __init__(self, root_dir):
        self._pods = self.get_repo_dir(root_dir) / 'pods'

    def get_pods_dir(self, pod_name):
        """Return path to the directory of pods."""
        return self._pods / pod_name

    def _get_pod_dirs(self, pod_name):
        """Return paths to the pod directory."""
        pods_dir = self.get_pods_dir(pod_name)
        try:
            return sorted(pods_dir.iterdir(), key=lambda p: p.name)
        except FileNotFoundError:
            LOG.warning('cannot list directory: %s', pods_dir)
            return []

    def _get_pod_dir(self, pod_name, version):
        return self._pods / pod_name / version

    @staticmethod
    def _get_pod(pod_dir):
        pod_data = json.loads((pod_dir / models.POD_JSON).read_text())
        return models.Pod(pod_data, pod_dir)

    def get_pod_names(self):
        try:
            return sorted(path.name for path in self._pods.iterdir())
        except FileNotFoundError:
            LOG.warning('cannot list directory: %s', self._pods)
            return []

    def iter_pods(self, pod_name):
        for pod_dir in self._get_pod_dirs(pod_name):
            yield self._get_pod(pod_dir)

    def get_pod_from_tag(self, tag):
        pod_name, version = tag.rsplit(':', 1)
        pod_dir = self._get_pod_dir(pod_name, version)
        scripts.ensure_directory(pod_dir)
        return self._get_pod(pod_dir)

    def get_pod_state(self, pod_or_tag):
        if isinstance(pod_or_tag, str):
            pod = None
            pod_name, version = pod_or_tag.rsplit(':', 1)
        else:
            pod = pod_or_tag
            pod_name = pod_or_tag.name
            version = pod_or_tag.version

        pod_dir = self._get_pod_dir(pod_name, version)
        if not pod_dir.exists():
            return PodState.UNDEPLOYED

        if pod is None:
            pod = self._get_pod(pod_dir)

        all_active = True
        for unit in pod.systemd_units:
            for unit_name in unit.unit_names:
                if not scripts.systemctl_is_active(unit_name):
                    LOG.debug('unit is not active: %s', unit_name)
                    all_active = False

        return PodState.STARTED if all_active else PodState.DEPLOYED

    def get_pod_dir(self, pod):
        return self._get_pod_dir(pod.name, pod.version)

    def get_ports(self):
        """Return an index of port allocations."""
        pods_and_manifests = []
        for name in self.get_pod_names():
            for pod_dir in self._get_pod_dirs(name):
                manifest_path = pod_dir / models.POD_MANIFEST_JSON
                if manifest_path.exists():
                    version = pod_dir.name
                    pods_and_manifests.append((
                        name,
                        version,
                        json.loads(manifest_path.read_text()),
                    ))
        return Ports(pods_and_manifests)


class Ports:
    """Index of port number allocations.

    Port numbers of this range [30000, 32768) are reserved for
    allocation at deployment time.  It is guaranteed that allocated port
    numbers are unique among all deployed pods so that reverting a pod
    version would not result in port number conflicts.

    On the other hand, port numbers out of this range are expected to be
    assigned statically in pod manifests - they might conflict if not
    planned and coordinated carefully.
    """

    PORT_MIN = 30000
    PORT_MAX = 32768

    Port = namedtuple('Port', [
        'pod_name',
        'pod_version',
        'name',
        'port',
    ])

    def __init__(self, pods_and_manifests):
        """Build index from generated pod manifest of deployed pods."""
        self._allocated_ports = {}
        self._static_ports = {}
        for pod_name, pod_version, manifest in pods_and_manifests:
            for port_data in manifest.get('ports', ()):
                port = self.Port(
                    pod_name=pod_name,
                    pod_version=pod_version,
                    name=port_data['name'],
                    port=int(port_data['hostPort']),
                )
                if self.PORT_MIN <= port.port < self.PORT_MAX:
                    if port.port in self._allocated_ports:
                        raise ValueError('duplicated port: {}'.format(port))
                    self._allocated_ports[port.port] = port
                else:
                    if port.port in self._static_ports:
                        raise ValueError('duplicated port: {}'.format(port))
                    self._static_ports[port.port] = port
        if self._allocated_ports:
            self._last_port = max(self._allocated_ports)
        else:
            self._last_port = -1

    def __iter__(self):
        ports = list(self._static_ports.values())
        ports.extend(self._allocated_ports.values())
        ports.sort()
        yield from ports

    def next_available_port(self):
        """Return next unallocated port number."""
        if self._last_port < self.PORT_MIN:
            return self.PORT_MIN
        elif self._last_port < self.PORT_MAX - 1:
            return self._last_port + 1
        else:
            return self._scan_port_numbers()

    def _scan_port_numbers(self):
        """Find next available port the slow way."""
        for port_number in range(self.PORT_MIN, self.PORT_MAX):
            if port_number not in self._allocated_ports:
                return port_number
        raise RuntimeError('no port available within range: %d ~ %d' %
                           (self.PORT_MIN, self.PORT_MAX))

    def register(self, port):
        """Claim a port as allocated."""
        if self.is_allocated(port.port):
            raise ValueError('port has been allocated: {}'.format(port))
        self._allocated_ports[port.port] = port
        self._last_port = max(self._last_port, port.port)

    def is_allocated(self, port_number):
        return (
            port_number in self._static_ports or
            port_number in self._allocated_ports
        )
