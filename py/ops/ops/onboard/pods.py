__all__ = [
    'pods',
]

from pathlib import Path
import json
import logging

from garage import cli, scripts
from garage.components import ARGS

from ops import models
from . import repos


LOG = logging.getLogger(__name__)


# Note that
#   deploy_copy
#   deploy_create_pod_manifest
#   deploy_create_volumes
#   deploy_fetch
# and
#   undeploy_remove
# are inverse operations to each other.


### Deploy


def deploy_copy(repo, bundle_pod):
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

    pod_dir = repo.get_pod_dir(bundle_pod)
    if pod_dir.exists():
        raise RuntimeError('attempt to overwrite dir: %s' % pod_dir)

    local_pod = bundle_pod.make_local_pod(pod_dir)

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
        assert len(bundle_pod.systemd_units) == len(local_pod.systemd_units)
        pairs = zip(bundle_pod.systemd_units, local_pod.systemd_units)
        for bundle_unit, local_unit in pairs:
            assert bundle_unit.unit_name == local_unit.unit_name
            _cp_or_wget(bundle_unit, 'unit_file', local_unit.unit_file_path)
            if local_unit.checksum:
                scripts.ensure_checksum(
                    local_unit.unit_file_path, local_unit.checksum)

        # Copy image files (but if it's URI, leave it to `rkt fetch`)
        scripts.mkdir(local_pod.pod_images_path)
        assert len(bundle_pod.images) == len(local_pod.images)
        pairs = zip(bundle_pod.images, local_pod.images)
        for bundle_image, local_image in pairs:
            assert bundle_image.id == local_image.id
            if bundle_image.image_path:
                scripts.cp(bundle_image.image_path, local_image.image_path)
            if bundle_image.signature:
                scripts.cp(bundle_image.signature, local_image.signature)

        # Copy volume data
        scripts.mkdir(local_pod.pod_volume_data_path)
        assert len(bundle_pod.volumes) == len(local_pod.volumes)
        pairs = zip(bundle_pod.volumes, local_pod.volumes)
        for bundle_volume, local_volume in pairs:
            assert bundle_volume.name == local_volume.name
            _cp_or_wget(bundle_volume, 'data', local_volume.data_path)
            if local_volume.checksum:
                scripts.ensure_checksum(
                    local_volume.data_path, local_volume.checksum)

    return local_pod


def deploy_create_pod_manifest(repo, pod):
    LOG.info('%s - create pod manifest', pod)
    scripts.ensure_directory(repo.get_pod_dir(pod))

    # Deployment-time volume allocation
    get_volume_path = lambda volume: pod.pod_volumes_path / volume.name

    # Deployment-time port allocation
    ports = repo.get_ports()
    def get_host_port(port_name):
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
            assert image.image_uri
            if image.image_uri.startswith('docker://'):
                cmd.append('--insecure-options=image')
            cmd.append(image.image_uri)
        scripts.execute(cmd)


def deploy_enable(pod):
    """Copy systemd unit files to /etc and enable units (but do not
       start them yet).
    """
    LOG.info('%s - enable pod', pod)
    for unit in pod.systemd_units:
        # Copy unit files
        # TODO: Don't use `systemctl link` for now and figure out why it
        # doesn't behave as I expect
        scripts.ensure_file(unit.unit_file_path)
        with scripts.using_sudo():
            scripts.cp(unit.unit_file_path, unit.unit_path)
            _make_dropin_file(pod, unit)
        # State: disabled -> enabled
        _change_unit_state(
            unit,
            'disabled',
            lambda name: not scripts.systemctl_is_enabled(name),
            scripts.systemctl_enable,
        )
        _ensure_unit_state(unit, 'enabled', scripts.systemctl_is_enabled)


def deploy_start(pod):
    """Start systemd units of the pod."""
    LOG.info('%s - start pod', pod)
    for unit in pod.systemd_units:
        # State: enabled -> active
        _change_unit_state(
            unit,
            'enabled',
            scripts.systemctl_is_enabled,
            scripts.systemctl_start,
        )
        _ensure_unit_state(unit, 'active', scripts.systemctl_is_active)


### Undeploy


# NOTE: These undeploy functions are resilient against the situations
# that pod state is unexpected (e.g., undeploy_stop is called when pod
# state is UNDEPLOYED).  Meaning, you may call them without ensuring pod
# state beforehand.


def undeploy_stop(pod):
    """Stop systemd units of the pod."""
    LOG.info('%s - stop pod', pod)
    for unit in pod.systemd_units:
        # State: active -> enabled
        _change_unit_state(
            unit,
            'active',
            scripts.systemctl_is_active,
            scripts.systemctl_stop,
        )


def undeploy_disable(pod):
    """Disable systemd units and remove unit files from /etc."""
    LOG.info('%s - disable pod', pod)
    for unit in pod.systemd_units:
        # State: enabled -> disabled
        _change_unit_state(
            unit,
            'enabled',
            scripts.systemctl_is_enabled,
            scripts.systemctl_disable,
        )
        # Remove unit files
        with scripts.using_sudo():
            scripts.rm(unit.unit_path)
            scripts.rm(unit.dropin_path, recursive=True)


def undeploy_remove(repo, pod):
    """Remove container images and the pod directory."""
    LOG.info('%s - remove pod', pod)

    # Undo deploy_fetch
    for image in pod.images:
        cmd = ['rkt', 'image', 'rm', image.id]
        if scripts.execute(cmd, check=False).returncode != 0:
            LOG.warning('cannot remove image: %s', image.id)

    # Undo deploy_copy and related actions, and if this is the last pod,
    # remove the pods directory, too
    with scripts.using_sudo():
        scripts.rm(repo.get_pod_dir(pod), recursive=True)
        scripts.rmdir(repo.get_pods_dir(pod.name))


### Command-line interface


argument_tag = cli.argument('tag', help='set pod tag (format "name:version")')


@cli.command('list', help='list deployed pods')
def list_pods(repo):
    """List deployed pods."""
    for pod_name in repo.get_pod_names():
        for pod in repo.iter_pods(pod_name):
            print(pod)
    return 0


@cli.command('is-undeployed', help='check if a pod is undeployed')
@argument_tag
def is_undeployed(args: ARGS, repo):
    """Check if a pod is undeployed."""
    if repo.get_pod_state(args.tag) is repos.PodState.UNDEPLOYED:
        return 0
    else:
        return 1


@cli.command('is-deployed', help='check if a pod is deployed')
@argument_tag
def is_deployed(args: ARGS, repo):
    """Check if a pod is deployed."""
    if repo.get_pod_state(args.tag) is repos.PodState.DEPLOYED:
        return 0
    else:
        return 1


@cli.command('is-started', help='check if a pod is started')
@argument_tag
def is_started(args: ARGS, repo):
    """Check if a pod is started."""
    if repo.get_pod_state(args.tag) is repos.PodState.STARTED:
        return 0
    else:
        return 1


@cli.command(help='deploy a pod')
@cli.argument('pod_file', type=Path, help='set path to the pod file')
def deploy(args: ARGS, repo):
    """Deploy a pod from a bundle."""

    pod_file = args.pod_file
    if pod_file.is_dir():
        pod_file = pod_file / models.POD_JSON
    scripts.ensure_file(pod_file)

    pod_data = json.loads(pod_file.read_text())
    pod = models.Pod(pod_data, pod_file.parent.absolute())

    pod_state = repo.get_pod_state(pod)
    if pod_state in (repos.PodState.DEPLOYED, repos.PodState.STARTED):
        LOG.info('%s - pod has been deployed', pod)
        return 0
    assert pod_state is repos.PodState.UNDEPLOYED

    LOG.info('%s - deploy', pod)
    try:
        pod = deploy_copy(repo, pod)
        deploy_create_pod_manifest(repo, pod)
        deploy_create_volumes(pod)
        deploy_fetch(pod)
    except Exception:
        undeploy_remove(repo, pod)
        raise

    return 0


@cli.command(help='start a pod')
@cli.argument(
    '--force', action='store_true',
    help='force start even if the pod has been started'
)
@argument_tag
def start(args: ARGS, repo):
    """Start a deployed pod."""

    pod_state = repo.get_pod_state(args.tag)
    if pod_state is repos.PodState.UNDEPLOYED:
        LOG.error('%s - pod has not been deployed', args.tag)
        return 1
    elif pod_state is repos.PodState.STARTED:
        LOG.info('%s - pod has been started', args.tag)
        if not args.force:
            return 0
    assert args.force or pod_state is repos.PodState.DEPLOYED

    pod = repo.get_pod_from_tag(args.tag)
    LOG.info('%s - start', pod)
    try:
        deploy_enable(pod)
        deploy_start(pod)
    except Exception:
        undeploy_stop(pod)
        undeploy_disable(pod)
        raise

    return 0


@cli.command(help='stop a pod')
@argument_tag
def stop(args: ARGS, repo):
    """Stop a started pod."""
    try:
        pod = repo.get_pod_from_tag(args.tag)
    except FileNotFoundError:
        LOG.warning('%s - pod has not been deployed', args.tag)
        return 0
    LOG.info('%s - stop', pod)
    undeploy_stop(pod)
    undeploy_disable(pod)
    return 0


@cli.command(help='undeploy a pod')
@argument_tag
def undeploy(args: ARGS, repo):
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


@cli.command(help='clean up pods')
@cli.argument(
    '--keep', type=int, default=8,
    help='keep latest number of versions (default to %(default)d)'
)
def cleanup(args: ARGS, repo):
    """Clean up undeployed pods."""
    if args.keep < 0:
        raise ValueError('negative keep: %d' % args.keep)
    for pod_name in repo.get_pod_names():
        LOG.info('%s - cleanup', pod_name)
        all_pods = list(reversed(repo.iter_pods(pod_name)))
        for pod in all_pods[args.keep:]:
            undeploy_stop(pod)
            undeploy_disable(pod)
            undeploy_remove(repo, pod)
    return 0


@cli.command(help='manage pods')
@cli.sub_command_info('operation', 'operation on external dependencies')
@cli.sub_command(list_pods)
@cli.sub_command(is_undeployed)
@cli.sub_command(is_deployed)
@cli.sub_command(is_started)
@cli.sub_command(deploy)
@cli.sub_command(start)
@cli.sub_command(stop)
@cli.sub_command(undeploy)
@cli.sub_command(cleanup)
def pods(args: ARGS):
    """Manage containerized application pods."""
    repo = repos.Repo(args.root)
    return args.operation(repo=repo)


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


def _ensure_unit_state(unit, state_name, predicate):
    errors = []
    for unit_name in unit.unit_names:
        if not predicate(unit_name):
            errors.append(unit_name)
    if errors:
        raise RuntimeError(
            'unit is not %s: %s' % (state_name, ', '.join(errors)))


def _change_unit_state(unit, state_name, predicate, actuator):
    for unit_name in unit.unit_names:
        if predicate(unit_name):
            with scripts.using_sudo():
                actuator(unit_name)
            if predicate(unit_name):
                LOG.warning('unit is still %s: %s', state_name, unit_name)
        else:
            LOG.warning('unit is not %s: %s', state_name, unit_name)