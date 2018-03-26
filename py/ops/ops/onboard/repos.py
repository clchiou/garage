"""Pod repository."""

__all__ = [
    'Ports',
    'Repo',
]

from collections import defaultdict, namedtuple
import json
import logging

from garage import scripts

from ops import models


# This is the version of the file layout.
VERSION = 1


LOG = logging.getLogger(__name__)


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

    def get_pod_dir(self, pod):
        return self._get_pod_dir(pod.name, pod.version)

    def get_images(self):
        """Return a (deployed) image-to-pods table."""
        table = defaultdict(list)
        for name in self.get_pod_names():
            for pod_dir in self._get_pod_dirs(name):
                manifest_path = pod_dir / models.POD_JSON
                if not manifest_path.exists():
                    continue
                version = pod_dir.name
                manifest = json.loads(manifest_path.read_text())
                for image in manifest.get('images', ()):
                    table[image['id']].append((name, version))
        for podvs in table.values():
            podvs.sort()
        return table

    def get_ports(self):
        """Return an index of port allocations."""

        pods_and_manifests = []

        def add_manifest(pod, manifest_path):
            if not manifest_path.exists():
                # While we are deploying this pod, its pod manifest may
                # have not been generated yet and we cannot add it to
                # the port index.
                LOG.debug('no such manifest: %s', manifest_path)
                return
            manifest = json.loads(manifest_path.read_text())
            pods_and_manifests.append((pod.name, pod.version, manifest))

        for pod_name in self.get_pod_names():
            for pod in self.iter_pods(pod_name):
                add_manifest(pod, pod.pod_manifest_path)
                for instance in pod.iter_instances():
                    add_manifest(pod, pod.get_pod_manifest_path(instance))

        return Ports(pods_and_manifests)

    def is_pod_tag_deployed(self, tag):
        try:
            pod = self.get_pod_from_tag(tag)
        except FileNotFoundError:
            LOG.debug('no such pod: %s', tag)
            return False
        return self.is_pod_deployed(pod)

    def is_pod_deployed(self, pod):
        deployed = True
        pod_dir = self.get_pod_dir(pod)
        if not pod_dir.exists():
            LOG.debug('no pod dir: %s', pod_dir)
            deployed = False
        # TODO: Check whether all images are fetched.
        for unit in pod.systemd_units:
            if not unit.is_installed():
                LOG.debug('unit is not installed: %s', unit.unit_name)
                deployed = False
        return deployed


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
                    prev = self._allocated_ports.get(port.port)
                    if prev is not None:
                        if prev == port:
                            # If it is from the same pod, I assume you
                            # know what you are doing (you've enabled
                            # SO_REUSEPORT, right?) and just issue a
                            # warning.
                            LOG.warning('duplicated port: %s', port)
                        else:
                            raise ValueError(
                                'duplicated port: {}'.format(port))
                    else:
                        LOG.debug('add port: %s', port)
                        self._allocated_ports[port.port] = port
                else:
                    prev = self._static_ports.get(port.port)
                    if prev is not None:
                        if prev == port:
                            # If it is from the same pod, I assume you
                            # know what you are doing (you've enabled
                            # SO_REUSEPORT, right?) and just issue a
                            # warning.
                            LOG.warning('duplicated static port: %s', port)
                        else:
                            raise ValueError(
                                'duplicated static port: {}'.format(port))
                    else:
                        LOG.debug('add static port: %s', port)
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
