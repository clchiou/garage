"""Pod repository."""

__all__ = [
    'Ports',
    'Repo',
]

import json
import logging
from collections import namedtuple

from ops.pods.models import Pod
from ops.version import get_data_dir


LOG = logging.getLogger(__name__)


class Repo:
    """The central repository of pods.

       Each pod stores its data under:
         ${DATA_DIR}/pods/${POD}/${VERSION}/...
    """

    def __init__(self, ops_data):
        self._pods_dir = get_data_dir(ops_data) / 'pods'

    def _get_pod_dir(self, pod_name, version):
        return self._pods_dir / pod_name / str(version)

    # Most methods should expect Pod object in their arguments except
    # these few methods below.

    def get_all_pod_names(self):
        try:
            return sorted(path.name for path in self._pods_dir.iterdir())
        except FileNotFoundError:
            LOG.warning('cannot list directory: %s', self._pods_dir)
            return []

    def get_pod_versions(self, pod_name):
        path = self._pods_dir / pod_name
        try:
            versions = sorted(int(p.name) for p in path.iterdir())
        except FileNotFoundError:
            LOG.warning('cannot list directory: %s', path)
            versions = []
        return versions

    def iter_pods_from_name(self, pod_name):
        for version in self.get_pod_versions(pod_name):
            yield Pod.load_json(self._get_pod_dir(pod_name, version))

    def get_pod_from_tag(self, tag):
        pod_name, version = tag.rsplit(':', 1)
        return Pod.load_json(self._get_pod_dir(pod_name, int(version)))

    def is_pod_deployed(self, pod_or_tag):
        if isinstance(pod_or_tag, str):
            pod_name, version = pod_or_tag.rsplit(':', 1)
        else:
            pod_name = pod_or_tag.name
            version = pod_or_tag.version
        pod_dir = self._get_pod_dir(pod_name, version)
        return pod_dir.exists()

    def get_pod_parent_dir(self, pod):
        return self._pods_dir / pod.name

    def get_pod_dir(self, pod):
        return self._get_pod_dir(pod.name, pod.version)

    def get_ports(self):
        """Return an index of port allocations."""
        pods_and_manifests = []
        for name in self.get_all_pod_names():
            for version in self.get_pod_versions(name):
                manifest_path = \
                    self._get_pod_dir(name, version) / Pod.POD_MANIFEST_JSON
                if manifest_path.exists():
                    pods_and_manifests.append((
                        name,
                        version,
                        json.loads(manifest_path.read_text()),
                    ))
        return Ports(pods_and_manifests)


class Ports:
    """Index of port number allocations.

       Port numbers of this range [30000, 32768) are reserved for
       allocation at deployment time.  It is guaranteed that allocated
       port numbers are unique among current and non-current pods (but
       not removed pods) so that reverting a pod would not result in
       port number conflicts with other pods.

       On the other hand, port numbers out of this range are expected to
       be assigned statically in pod manifests - they might conflict if
       not planned and coordinated carefully.
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
        """Build index from generated Appc manifest of deployed pods,
           not from the "abstract" manifest object of pod objects.
        """
        self._static_ports = []
        self._index = {}
        for pod_name, pod_version, manifest in pods_and_manifests:
            for port_data in manifest.get('ports', ()):
                port = self.Port(
                    pod_name=pod_name,
                    pod_version=pod_version,
                    name=port_data['name'],
                    port=int(port_data['hostPort']),
                )
                if not self.PORT_MIN <= port.port < self.PORT_MAX:
                    self._static_ports.append(port)
                else:
                    if port.port in self._index:
                        raise ValueError('duplicated port: {}'.format(port))
                    self._index[port.port] = port
        self._last_port = max(self._index) if self._index else -1

    def __iter__(self):
        yield from self._static_ports
        for port in sorted(self._index):
            yield self._index[port]

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
            if port_number not in self._index:
                return port_number
        raise RuntimeError('no port available within range: %d ~ %d' %
                           (self.PORT_MIN, self.PORT_MAX))

    def register(self, port):
        """Claim a port as allocated."""
        if not self.PORT_MIN <= port.port < self.PORT_MAX:
            raise ValueError('not in reserved port range: {}'.format(port))
        if port.port in self._index:
            raise ValueError('port has been allocated: {}'.format(port))
        self._index[port.port] = port
        self._last_port = max(self._last_port, port.port)
