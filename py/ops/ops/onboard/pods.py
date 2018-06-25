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
from . import deps
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
    get_volume_path = lambda _, volume: pod.pod_volumes_path / volume.name

    # Deployment-time port allocation.
    ports = repo.get_ports()
    def get_host_port(instance, port_name):

        for port_allocation in pod.ports:
            if port_allocation.name == port_name:
                break
        else:
            port_allocation = None

        if port_allocation:
            # Okay, this is a statically assigned port; pick the first
            # unassigned port number.
            for port_number in port_allocation.host_ports:
                if not ports.is_assigned(port_number):
                    break
            else:
                port_number = port_allocation.host_ports[0]
                LOG.info(
                    'all are assigned; re-use the first one: %d',
                    port_number,
                )
            action_name = 'assign'
            action = ports.assign

        else:
            port_number = ports.next_available_port()
            action_name = 'allocate'
            action = ports.allocate

        LOG.info(
            '%s%s%s - %s %s port %d',
            pod,
            ' ' if instance.name else '',
            instance.name or '',
            action_name,
            port_name,
            port_number,
        )
        action(ports.Port(
            pod_name=pod.name,
            pod_version=pod.version,
            instance=instance.name,
            name=port_name,
            port=port_number,
        ))

        return port_number

    with scripts.using_sudo():
        scripts.mkdir(pod.pod_manifests_path)
        for instance in pod.iter_instances():
            # Generate Appc pod manifest.
            manifest_base = json.dumps(
                pod.make_manifest(
                    instance=instance,
                    get_volume_path=get_volume_path,
                    get_host_port=get_host_port,
                ),
                indent=4,
                sort_keys=True,
            )
            # TODO It might not be a great idea to do text substitution
            # on JSON string, but it seems to be the only way to
            # customize pod instances, and probably relatively safe to
            # do.  Hopefully I will find another way without text
            # substitution.
            manifest = instance.resolve_specifier(manifest_base)
            scripts.tee(
                manifest.encode('ascii'),
                pod.get_pod_manifest_path(instance),
            )


def deploy_create_volumes(pod):
    """Create volumes under POD_DIR/volumes."""
    LOG.info('%s - create data volumes', pod)
    with scripts.using_sudo():
        volume_root = pod.pod_volumes_path
        for volume in pod.volumes:
            _create_volume(volume_root, volume)


def deploy_fetch(pod, *, image_ids=None):
    """Fetch container images from local files or from remote."""
    LOG.info('%s - fetch images', pod)
    if image_ids is None:
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
    with scripts.using_sudo():
        scripts.systemctl_daemon_reload()


def deploy_enable(pod, *, predicate=None):
    """Enable default systemd unit instances."""
    LOG.info('%s - enable pod units', pod)
    predicate = predicate or pod.should_but_not_enabled
    for instance in pod.filter_instances(predicate):
        LOG.info('%s - enable unit instance: %s', pod, instance.unit_name)
        with scripts.using_sudo():
            scripts.systemctl_enable(instance.unit_name)
            if not scripts.systemctl_is_enabled(instance.unit_name):
                raise RuntimeError(
                    'unit %s is not enabled' % instance.unit_name)


def deploy_start(pod, *, predicate=None):
    """Start default systemd unit instances."""
    LOG.info('%s - start pod units', pod)
    predicate = predicate or pod.should_but_not_started
    for instance in pod.filter_instances(predicate):
        LOG.info('%s - start unit instance: %s', pod, instance.unit_name)
        with scripts.using_sudo():
            scripts.systemctl_start(instance.unit_name)
            if not scripts.systemctl_is_active(instance.unit_name):
                raise RuntimeError(
                    'unit %s is not started' % instance.unit_name)


### Undeploy


# NOTE: These undeploy functions are resilient against the situations
# that pod state is unexpected (e.g., undeploy_stop is called when pod
# state is UNDEPLOYED).  Meaning, you may call them without ensuring pod
# state beforehand.


def undeploy_stop(pod, *, predicate=None):
    """Stop all systemd units of the pod (regardless default)."""
    LOG.info('%s - stop pod units', pod)
    for instance in pod.filter_instances(predicate):
        LOG.info('%s - stop unit instance: %s', pod, instance.unit_name)
        with scripts.checking(False), scripts.using_sudo():
            scripts.systemctl_stop(instance.unit_name)
            if scripts.systemctl_is_active(instance.unit_name):
                LOG.warning('unit %s is still active', instance.unit_name)


def undeploy_disable(pod, *, predicate=None):
    """Disable all systemd units of the pod (regardless default)."""
    LOG.info('%s - disable pod units', pod)
    for instance in pod.filter_instances(predicate):
        LOG.info('%s - disable unit instance: %s', pod, instance.unit_name)
        with scripts.checking(False), scripts.using_sudo():
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
            for instance in unit.instances:
                scripts.rm(instance.dropin_path, recursive=True)
    with scripts.checking(False), scripts.using_sudo():
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


with_argument_instance = apps.with_decorators(
    apps.with_argument(
        '--instance-all', action='store_true',
        help='select all instances',
    ),
    apps.with_argument(
        '--instance', action='append',
        help='select instance(s) by name (the part after "@")',
    ),
)


with_argument_tag = apps.with_argument(
    'tag',
    help='set pod tag (format "name@version")',
)


@apps.with_prog('list')
@apps.with_help('list deployed pods')
@apps.with_argument(
    '--show-state', action='store_true',
    help='also print unit state',
)
def list_pods(args, repo):
    """List deployed pods."""
    for pod_dir_name in repo.get_pod_dir_names():
        for pod in repo.iter_pods(pod_dir_name):
            row = [pod]
            if args.show_state:
                if pod.is_enabled():
                    row.append('enabled')
                if pod.is_started():
                    row.append('started')
            print(*row)
    return 0


@apps.with_prog('list-units')
@apps.with_help('list systemd units of deployed pods')
@apps.with_argument(
    '--show-state', action='store_true',
    help='also print unit state',
)
def list_units(args, repo):
    """List systemd units of deployed pods."""
    for pod_dir_name in repo.get_pod_dir_names():
        for pod in repo.iter_pods(pod_dir_name):
            for instance in pod.iter_instances():
                row = [pod, instance.unit_name]
                if args.show_state:
                    if scripts.systemctl_is_enabled(instance.unit_name):
                        row.append('enabled')
                    if scripts.systemctl_is_active(instance.unit_name):
                        row.append('started')
                print(*row)
    return 0


@apps.with_prog('is-deployed')
@apps.with_help('check if a pod is deployed')
@with_argument_tag
def is_deployed(args, repo):
    """Check if a pod is deployed."""
    if repo.is_pod_tag_deployed(args.tag):
        return 0
    else:
        return 1


@apps.with_prog('is-enabled')
@apps.with_help('check if default unit instances are enabled')
@with_argument_instance
@with_argument_tag
def is_enabled(args, repo):
    """Check if default unit instances are enabled."""
    return _check_pod_state(args, repo, models.Pod.is_enabled)


@apps.with_prog('is-started')
@apps.with_help('check if default unit instances are started')
@with_argument_instance
@with_argument_tag
def is_started(args, repo):
    """Check if default unit instances are started."""
    return _check_pod_state(args, repo, models.Pod.is_started)


def _check_pod_state(args, repo, check_state):
    try:
        pod = repo.get_pod_from_tag(args.tag)
    except FileNotFoundError:
        LOG.debug('no pod dir for: %s', args.tag)
        return 1
    if check_state(pod, predicate=_make_instance_predicate(args)):
        return 0
    else:
        return 1


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

    if repo.is_pod_deployed(pod):
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
@with_argument_instance
@with_argument_tag
def enable(args, repo):
    """Enable a deployed pod."""
    return _deploy_operation(
        args, repo, 'enable', deploy_enable, undeploy_disable)


@apps.with_help('start a pod')
@with_argument_instance
@with_argument_tag
def start(args, repo):
    """Start a deployed pod."""
    return _deploy_operation(args, repo, 'start', deploy_start, undeploy_stop)


def _deploy_operation(args, repo, operator_name, operator, reverse_operator):
    pod = repo.get_pod_from_tag(args.tag)
    LOG.info('%s - %s', pod, operator_name)
    try:
        operator(pod, predicate=_make_instance_predicate(args))
    except Exception:
        # XXX I do not know if this is a good idea, but on error, I will
        # reverse (disable or stop) all instances.
        reverse_operator(pod)
        raise
    return 0


@apps.with_help('stop a pod')
@with_argument_instance
@with_argument_tag
def stop(args, repo):
    """Stop a pod."""
    return _undeploy_operation(args, repo, 'stop', undeploy_stop)


@apps.with_help('disable a pod')
@with_argument_instance
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
    operator(pod, predicate=_make_instance_predicate(args))
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

    def _is_enabled_or_started(pod):
        for instance in pod.iter_instances():
            if scripts.systemctl_is_enabled(instance.unit_name):
                return True
            if scripts.systemctl_is_active(instance.unit_name):
                return True
        return False

    for pod_dir_name in repo.get_pod_dir_names():
        LOG.info('%s - cleanup', pod_dir_name)
        all_pods = list(repo.iter_pods(pod_dir_name))
        num_left = len(all_pods)
        for pod in all_pods:
            if num_left <= args.keep:
                break
            if _is_enabled_or_started(pod):
                LOG.info('refuse to undeploy pod: %s', pod)
                continue
            undeploy_stop(pod)
            undeploy_disable(pod)
            undeploy_remove(repo, pod)
            num_left -= 1

    return 0


@apps.with_help('manage pods')
@apps.with_apps(
    'operation', 'operation on pods',
    list_pods,
    list_units,
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


@apps.with_prog('refetch-all')
@apps.with_help('re-fetch all container images')
def refetch_all(args):
    """Re-fetch all container images.

    Use this to work around the known issue that `rkt image gc` also
    collects still-in-use images.
    """
    scripts.execute([
        'rkt', 'fetch',
        'coreos.com/rkt/stage1-coreos:' + deps.PACKAGES['rkt'].version,
    ])
    repo = repos.Repo(args.root)
    image_ids = _list_image_ids()
    for pod_dir_name in repo.get_pod_dir_names():
        for pod in repo.iter_pods(pod_dir_name):
            deploy_fetch(pod, image_ids=image_ids)
    return 0


### Helper functions


def _make_instance_predicate(args):
    if args.instance_all:
        predicate = lambda _: True
    elif args.instance:
        instance_names = set(args.instance)
        predicate = lambda instance: instance.name in instance_names
    else:
        predicate = None
    return predicate


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
    contents = (
        '[Service]\n'
        'Environment="POD_MANIFEST={pod_manifest}"\n'
        # Metadata of this pod instance.
        'Environment="POD_NAME={pod_name}"\n'
        'Environment="POD_VERSION={pod_version}"\n'
    )
    for instance in unit.instances:
        scripts.mkdir(instance.dropin_path)
        scripts.tee(
            (contents
             .format(
                 pod_manifest=pod.get_pod_manifest_path(instance),
                 pod_name=pod.name,
                 pod_version=pod.version,
             )
             .encode('ascii')),
            instance.dropin_path / '10-pod-manifest.conf',
        )
