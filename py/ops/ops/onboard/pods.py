__all__ = [
    'pods',
]

from pathlib import Path
import json
import logging

from garage import apps
from garage import scripts
from garage.assertions import ASSERT

from ops import models
from . import repos


LOG = logging.getLogger(__name__)


# Note that
#   deploy_copy
#   deploy_create_pod_manifest
#   deploy_create_volumes
#   deploy_fetch
#   deploy_install_units
# and
#   undeploy_remove
# are inverse operations to each other.


### Deploy


def deploy_copy(_, bundle_pod, local_pod):
    """Copy pod data from bundle to the pod directory, and return a new
       pod object representing the pod directory.

       All remote files will be fetched and stored in the pod directory
       except images.

       Specifically, this will create these under POD_DIR:
       * pod.json
       * images/...
       * systemd/...
       * volume-data/...
    """
    LOG.info('%s - copy', bundle_pod)

    with scripts.using_sudo():

        # Generate new pod.json
        scripts.mkdir(local_pod.pod_object_path.parent)
        scripts.tee(
            (json.dumps(local_pod.to_pod_data(), indent=4, sort_keys=True)
             .encode('ascii')),
            local_pod.pod_object_path,
        )

        # Copy systemd unit files
        scripts.mkdir(local_pod.pod_systemd_path)
        ASSERT.equal(
            len(bundle_pod.systemd_units),
            len(local_pod.systemd_units),
        )
        pairs = zip(bundle_pod.systemd_units, local_pod.systemd_units)
        for bundle_unit, local_unit in pairs:
            ASSERT.equal(bundle_unit.unit_name, local_unit.unit_name)
            _cp_or_wget(bundle_unit, 'unit_file', local_unit.unit_file_path)
            if local_unit.checksum:
                scripts.ensure_checksum(
                    local_unit.unit_file_path, local_unit.checksum)

        # Copy image files (but if it's URI, leave it to `rkt fetch`)
        scripts.mkdir(local_pod.pod_images_path)
        ASSERT.equal(len(bundle_pod.images), len(local_pod.images))
        pairs = zip(bundle_pod.images, local_pod.images)
        for bundle_image, local_image in pairs:
            ASSERT.equal(bundle_image.id, local_image.id)
            if bundle_image.image_path:
                scripts.cp(bundle_image.image_path, local_image.image_path)
            if bundle_image.signature:
                scripts.cp(bundle_image.signature, local_image.signature)

        # Copy volume data
        scripts.mkdir(local_pod.pod_volume_data_path)
        ASSERT.equal(len(bundle_pod.volumes), len(local_pod.volumes))
        pairs = zip(bundle_pod.volumes, local_pod.volumes)
        for bundle_volume, local_volume in pairs:
            ASSERT.equal(bundle_volume.name, local_volume.name)
            _cp_or_wget(bundle_volume, 'data', local_volume.data_path)
            if local_volume.checksum:
                scripts.ensure_checksum(
                    local_volume.data_path, local_volume.checksum)

    return local_pod


def deploy_create_pod_manifest(repo, pod):
    LOG.info('%s - create pod manifest', pod)
    scripts.ensure_directory(repo.get_pod_dir(pod))

    # Deployment-time volume allocation.
    get_volume_path = lambda volume: pod.pod_volumes_path / volume.name

    # Deployment-time port allocation.
    ports = repo.get_ports()
    def get_host_port(port_name):

        for port_allocation in pod.ports:
            if port_allocation.name == port_name:
                break
        else:
            port_allocation = None

        if port_allocation:
            for port_number in port_allocation.host_ports:
                if not ports.is_allocated(port_number):
                    break
            else:
                raise RuntimeError(
                    'no host port reserved for %s is available' % port_name)

        else:
            port_number = ports.next_available_port()

        LOG.info('%s - allocate port %d for %s', pod, port_number, port_name)
        ports.register(ports.Port(
            pod_name=pod.name,
            pod_version=pod.version,
            name=port_name,
            port=port_number,
        ))
        return port_number

    # Generate Appc pod manifest
    manifest = json.dumps(
        pod.make_manifest(
            get_volume_path=get_volume_path,
            get_host_port=get_host_port,
        ),
        indent=4,
        sort_keys=True,
    )
    with scripts.using_sudo():
        scripts.tee(manifest.encode('ascii'), pod.pod_manifest_path)


def deploy_create_volumes(pod):
    """Create volumes under POD_DIR/volumes."""
    LOG.info('%s - create data volumes', pod)
    with scripts.using_sudo():
        volume_root = pod.pod_volumes_path
        for volume in pod.volumes:
            _create_volume(volume_root, volume)


def deploy_fetch(pod):
    """Fetch container images from local files or from remote."""
    LOG.info('%s - fetch images', pod)
    image_ids = _list_image_ids()
    for image in pod.images:
        if _match_image_id(image.id, image_ids):
            LOG.debug('skip fetching image %s', image.id)
            continue
        cmd = ['rkt', 'fetch']
        if image.signature:
            cmd.extend(['--signature', image.signature])
        if image.image_path:
            if not image.signature:
                LOG.warning('no signature for %s', image.image_path)
                cmd.append('--insecure-options=image')
            cmd.append(image.image_path)
        else:
            ASSERT.true(image.image_uri)
            if image.image_uri.startswith('docker://'):
                cmd.append('--insecure-options=image')
            cmd.append(image.image_uri)
        scripts.execute(cmd)


def deploy_install_units(pod):
    """Install and load systemd units."""
    for unit in pod.systemd_units:
        # TODO: Don't use `systemctl link` for now and figure out why it
        # doesn't behave as I expect.
        scripts.ensure_file(unit.unit_file_path)
        with scripts.using_sudo():
            scripts.cp(unit.unit_file_path, unit.unit_path)
            _make_dropin_file(pod, unit)
    scripts.systemctl_daemon_reload()


def deploy_enable(pod):
    """Enable default systemd units."""
    LOG.info('%s - enable pod', pod)
    for instance in pod.filter_instances(pod.should_but_not_enabled):
        scripts.systemctl_enable(instance.unit_name)
        if not scripts.systemctl_is_enabled(instance.unit_name):
            raise RuntimeError('unit %s is not enabled' % instance.unit_name)


def deploy_start(pod):
    """Start default systemd units."""
    LOG.info('%s - start pod', pod)
    for instance in pod.filter_instances(pod.should_but_not_started):
        scripts.systemctl_start(instance.unit_name)
        if not scripts.systemctl_is_active(instance.unit_name):
            raise RuntimeError('unit %s is not started' % instance.unit_name)


### Undeploy


# NOTE: These undeploy functions are resilient against the situations
# that pod state is unexpected (e.g., undeploy_stop is called when pod
# state is UNDEPLOYED).  Meaning, you may call them without ensuring pod
# state beforehand.


def undeploy_stop(pod):
    """Stop all systemd units of the pod (regardless default)."""
    LOG.info('%s - stop pod', pod)
    for instance in pod.iter_instances():
        scripts.systemctl_stop(instance.unit_name)
        if scripts.systemctl_is_active(instance.unit_name):
            LOG.warning('unit %s is still active', instance.unit_name)


def undeploy_disable(pod):
    """Disable all systemd units of the pod (regardless default)."""
    LOG.info('%s - disable pod', pod)
    for instance in pod.iter_instances():
        scripts.systemctl_disable(instance.unit_name)
        if scripts.systemctl_is_enabled(instance.unit_name):
            LOG.warning('unit %s is still enabled', instance.unit_name)


def undeploy_remove(repo, pod):
    """Remove container images and the pod directory."""
    LOG.info('%s - remove pod', pod)

    # Undo deploy_install_units.
    for unit in pod.systemd_units:
        with scripts.using_sudo():
            scripts.rm(unit.unit_path)
            scripts.rm(unit.dropin_path, recursive=True)
    scripts.systemctl_daemon_reload()

    image_to_pod_table = repo.get_images()

    # Undo deploy_fetch.
    for image in pod.images:
        if len(image_to_pod_table[image.id]) > 1:
            LOG.debug('not remove image which is still in use: %s', image.id)
            continue
        cmd = ['rkt', 'image', 'rm', image.id]
        if scripts.execute(cmd, check=False).returncode != 0:
            LOG.warning('cannot remove image: %s', image.id)

    # Undo deploy_copy and related actions, and if this is the last pod,
    # remove the pods directory, too.
    with scripts.using_sudo():
        scripts.rm(repo.get_pod_dir(pod), recursive=True)
        scripts.rmdir(repo.get_pods_dir(pod.name))


### Command-line interface


with_argument_tag = apps.with_argument(
    'tag',
    help='set pod tag (format "name:version")',
)


@apps.with_prog('list')
@apps.with_help('list deployed pods')
def list_pods(_, repo):
    """List deployed pods."""
    for pod_name in repo.get_pod_names():
        for pod in repo.iter_pods(pod_name):
            print(pod)
    return 0


@apps.with_prog('is-undeployed')
@apps.with_help('check if a pod is undeployed')
@with_argument_tag
def is_undeployed(args, repo):
    """Check if a pod is undeployed."""
    if not repo.get_pod_state(args.tag) & repos.PodState.DEPLOYED:
        return 0
    else:
        return 1


@apps.with_prog('is-deployed')
@apps.with_help('check if a pod is deployed')
@with_argument_tag
def is_deployed(args, repo):
    """Check if a pod is deployed."""
    return _check_pod_state(repo, args.tag, repos.PodState.DEPLOYED)


@apps.with_prog('is-enabled')
@apps.with_help('check if a pod is enabled')
@with_argument_tag
def is_enabled(args, repo):
    """Check if a pod is enabled."""
    return _check_pod_state(repo, args.tag, repos.PodState.ENABLED)


@apps.with_prog('is-started')
@apps.with_help('check if a pod is started')
@with_argument_tag
def is_started(args, repo):
    """Check if a pod is started."""
    return _check_pod_state(repo, args.tag, repos.PodState.STARTED)


def _check_pod_state(repo, tag, state):
    return 0 if repo.get_pod_state(tag) & state else 1


@apps.with_help('deploy a pod')
@apps.with_argument('pod_file', type=Path, help='set path to the pod file')
def deploy(args, repo):
    """Deploy a pod from a bundle."""

    pod_file = args.pod_file
    if pod_file.is_dir():
        pod_file = pod_file / models.POD_JSON
    scripts.ensure_file(pod_file)

    bundle_pod = models.Pod(
        json.loads(pod_file.read_text()),
        pod_file.parent.absolute(),
    )

    pod = bundle_pod.make_local_pod(repo.get_pod_dir(bundle_pod))

    pod_state = repo.get_pod_state(pod)
    if pod_state & repos.PodState.DEPLOYED:
        LOG.info('%s - pod has been deployed', pod)
        return 0

    LOG.info('%s - deploy', pod)
    try:
        deploy_copy(repo, bundle_pod, pod)
        deploy_create_pod_manifest(repo, pod)
        deploy_create_volumes(pod)
        deploy_fetch(pod)
        deploy_install_units(pod)
    except Exception:
        undeploy_remove(repo, pod)
        raise

    return 0


@apps.with_help('enable a pod')
@with_argument_tag
def enable(args, repo):
    """Enable a deployed pod."""
    return _deploy_operation(
        args, repo, 'enable', deploy_enable, undeploy_disable)


@apps.with_help('start a pod')
@with_argument_tag
def start(args, repo):
    """Start a deployed pod."""
    return _deploy_operation(args, repo, 'start', deploy_start, undeploy_stop)


def _deploy_operation(args, repo, operator_name, operator, reverse_operator):
    pod_state = repo.get_pod_state(args.tag)
    if not pod_state & repos.PodState.DEPLOYED:
        LOG.error('%s - pod has not been deployed', args.tag)
        return 1
    pod = repo.get_pod_from_tag(args.tag)
    LOG.info('%s - %s', pod, operator_name)
    try:
        operator(pod)
    except Exception:
        reverse_operator(pod)
        raise
    return 0


@apps.with_help('stop a pod')
@with_argument_tag
def stop(args, repo):
    """Stop a pod."""
    return _undeploy_operation(args, repo, 'stop', undeploy_stop)


@apps.with_help('disable a pod')
@with_argument_tag
def disable(args, repo):
    """Disable a pod."""
    return _undeploy_operation(args, repo, 'disable', undeploy_disable)


def _undeploy_operation(args, repo, operator_name, operator):
    try:
        pod = repo.get_pod_from_tag(args.tag)
    except FileNotFoundError:
        LOG.warning('%s - pod has not been deployed', args.tag)
        return 0
    LOG.info('%s - %s', pod, operator_name)
    operator(pod)
    return 0


@apps.with_help('undeploy a pod')
@with_argument_tag
def undeploy(args, repo):
    """Undeploy a deployed pod."""
    try:
        pod = repo.get_pod_from_tag(args.tag)
    except FileNotFoundError:
        LOG.warning('%s - pod has not been deployed', args.tag)
        return 0
    LOG.info('%s - undeploy', pod)
    undeploy_stop(pod)
    undeploy_disable(pod)
    undeploy_remove(repo, pod)
    return 0


@apps.with_help('clean up pods')
@apps.with_argument(
    '--keep', type=int, default=8,
    help='keep latest number of versions (default to %(default)d)'
)
def cleanup(args, repo):
    """Clean up undeployed pods."""
    if args.keep < 0:
        raise ValueError('negative keep: %d' % args.keep)
    for pod_name in repo.get_pod_names():
        LOG.info('%s - cleanup', pod_name)
        all_pods = list(repo.iter_pods(pod_name))
        all_pods.reverse()
        for pod in all_pods[args.keep:]:
            undeploy_stop(pod)
            undeploy_disable(pod)
            undeploy_remove(repo, pod)
    return 0


@apps.with_help('manage pods')
@apps.with_apps(
    'operation', 'operation on pods',
    list_pods,
    is_undeployed,
    is_deployed,
    is_enabled,
    is_started,
    deploy,
    enable,
    start,
    stop,
    disable,
    undeploy,
    cleanup,
)
def pods(args):
    """Manage containerized application pods."""
    repo = repos.Repo(args.root)
    return args.operation(args, repo=repo)


### Helper functions


def _list_image_ids():
    cmd = 'rkt image list --fields=id --full --no-legend'.split()
    output = scripts.execute(cmd, capture_stdout=True).stdout
    if not output:
        return ()
    output = output.decode('ascii')
    return frozenset(filter(None, map(str.strip, output.split('\n'))))


def _match_image_id(target_id, image_ids):
    for image_id in image_ids:
        if image_id.startswith(target_id) or target_id.startswith(image_id):
            return True
    return False


def _cp_or_wget(obj, name, dst):
    src_path = getattr(obj, name + '_path')
    if src_path:
        scripts.cp(src_path, dst)
        return True
    src_uri = getattr(obj, name + '_uri')
    if src_uri:
        scripts.wget(src_uri, dst)
        return True
    return False


def _create_volume(volume_root, volume):
    # Create volume directory and change its owner
    volume_path = volume_root / volume.name
    if volume_path.exists():
        raise RuntimeError('volume exists: %s' % volume_path)
    scripts.mkdir(volume_path)
    scripts.execute(
        ['chown', '%s:%s' % (volume.user, volume.group), volume_path])
    # Extract contents for volume
    if volume.data_path:
        scripts.tar_extract(
            volume.data_path,
            volume_path,
            tar_extra_flags=[
                # This is default when sudo but just be explicit
                '--preserve-permissions',
            ],
        )


def _make_dropin_file(pod, unit):
    scripts.mkdir(unit.dropin_path)
    scripts.tee(
        (('[Service]\n'
          'Environment="POD_MANIFEST={pod_manifest}"\n')
         .format(pod_manifest=pod.pod_manifest_path)
         .encode('ascii')),
        unit.dropin_path / '10-pod-manifest.conf',
    )
