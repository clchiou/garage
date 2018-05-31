"""Pod repository."""

__all__ = [
    'Ports',
    'Repo',
]

from collections import defaultdict, namedtuple
import json
import logging

from garage import scripts
from garage.assertions import ASSERT

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

    def get_pods_dir(self, pod_dir_name):
        """Return path to the directory of pods."""
        if isinstance(pod_dir_name, models.PodName):
            pod_dir_name = pod_dir_name.make_suitable_for_filename()
        return self._pods / pod_dir_name

    def _get_pod_dirs(self, pod_dir_name):
        """Return paths to the pod directory."""
        pods_dir = self.get_pods_dir(pod_dir_name)
        try:
            return sorted(pods_dir.iterdir(), key=lambda p: p.name)
        except FileNotFoundError:
            LOG.warning('cannot list directory: %s', pods_dir)
            return []

    def _get_pod_dir(self, pod_dir_name, version):
        return self._pods / pod_dir_name / version

    @staticmethod
    def _get_pod(pod_dir):
        pod_data = json.loads((pod_dir / models.POD_JSON).read_text())
        return models.Pod(pod_data, pod_dir)

    def get_pod_dir_names(self):
        try:
            return sorted(path.name for path in self._pods.iterdir())
        except FileNotFoundError:
            LOG.warning('cannot list directory: %s', self._pods)
            return []

    def iter_pods(self, pod_dir_name):
        for pod_dir in self._get_pod_dirs(pod_dir_name):
            yield self._get_pod(pod_dir)

    def get_pod_from_tag(self, tag):
        pod_name, version = tag.rsplit('@', 1)
        pod_dir = self._get_pod_dir(
            models.PodName(pod_name).make_suitable_for_filename(),
            version,
        )
        scripts.ensure_directory(pod_dir)
        return self._get_pod(pod_dir)

    def get_pod_dir(self, pod):
        return self._get_pod_dir(
            pod.name.make_suitable_for_filename(),
            pod.version,
        )

    def get_images(self):
        """Return a (deployed) image-to-pods table."""
        table = defaultdict(list)
        for pod_dir_name in self.get_pod_dir_names():
            for pod_dir in self._get_pod_dirs(pod_dir_name):
                manifest_path = pod_dir / models.POD_JSON
                if not manifest_path.exists():
                    continue
                version = pod_dir.name
                manifest = json.loads(manifest_path.read_text())
                pod_name = models.PodName(manifest['name'])
                for image in manifest.get('images', ()):
                    table[image['id']].append((pod_name, version))
        for podvs in table.values():
            podvs.sort()
        return table

    def get_ports(self):
        """Return an index of port allocations."""

        pods_and_manifests = []

        def add_manifest(pod, instance_name, manifest_path):
            if not manifest_path.exists():
                # While we are deploying this pod, its pod manifest may
                # have not been generated yet and we cannot add it to
                # the port index.
                LOG.debug('no such manifest: %s', manifest_path)
                return
            manifest = json.loads(manifest_path.read_text())
            pods_and_manifests.append(
                (pod.name, pod.version, instance_name, manifest))

        for pod_dir_name in self.get_pod_dir_names():
            for pod in self.iter_pods(pod_dir_name):
                for instance in pod.iter_instances():
                    add_manifest(
                        pod,
                        instance.name,
                        pod.get_pod_manifest_path(instance),
                    )

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
    assigned statically in pod manifests - you may assign the same port
    number to multiple pods, if you know what you are doing.
    """

    PORT_MIN = 30000
    PORT_MAX = 32768

    Port = namedtuple('Port', [
        'pod_name',
        'pod_version',
        'instance',
        'name',
        'port',
    ])

    def __init__(self, pods_and_manifests):
        """Build index from generated pod manifest of deployed pods."""

        # Ports allocated at Deployment time (from PORT_MIN to
        # PORT_MAX).  They are guaranteed to be unique among all pod
        # instances.
        self._allocated_ports = {}
        self._last_port = -1

        # Statically assigned ports.
        self._assigned_static_port_numbers = set()
        self._static_ports = []

        for item in pods_and_manifests:
            pod_name, pod_version, instance_name, manifest = item
            for port_data in manifest.get('ports', ()):
                port = self.Port(
                    pod_name=pod_name,
                    pod_version=pod_version,
                    instance=instance_name,
                    name=port_data['name'],
                    port=int(port_data['hostPort']),
                )
                if self.PORT_MIN <= port.port < self.PORT_MAX:
                    prev = self._allocated_ports.get(port.port)
                    if prev is not None:
                        raise ValueError(
                            'duplicated port: %s vs %s' % (prev, port))
                    LOG.debug('add allocated port: %s', port)
                    self._allocated_ports[port.port] = port
                else:
                    LOG.debug('add static port: %s', port)
                    self._assigned_static_port_numbers.add(port.port)
                    self._static_ports.append(port)

        if self._allocated_ports:
            self._last_port = max(self._allocated_ports)

    def __iter__(self):
        ports = list(self._static_ports)
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

    def is_allocated(self, port_number):
        ASSERT.true(self.PORT_MIN <= port_number < self.PORT_MAX)
        return port_number in self._allocated_ports

    def allocate(self, port):
        """Claim a port as allocated."""
        ASSERT.true(self.PORT_MIN <= port.port < self.PORT_MAX)
        if self.is_allocated(port.port):
            raise ValueError('port has been allocated: {}'.format(port))
        self._allocated_ports[port.port] = port
        self._last_port = max(self._last_port, port.port)

    def is_assigned(self, port_number):
        ASSERT.false(self.PORT_MIN <= port_number < self.PORT_MAX)
        return port_number in self._assigned_static_port_numbers

    def assign(self, port):
        ASSERT.false(self.PORT_MIN <= port.port < self.PORT_MAX)
        self._assigned_static_port_numbers.add(port.port)
        self._static_ports.append(port)
