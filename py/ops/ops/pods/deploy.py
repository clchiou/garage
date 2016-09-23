"""Deployment commands."""

__all__ = [
    'deploy',
    'start',
    'stop',
    'undeploy',
    'cleanup',
]

import json
import logging
import urllib.parse
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

from ops import scripting
from ops.pods import models
from ops.pods import repos


LOG = logging.getLogger(__name__)


# Note that
#   deploy_fetch + deploy_install + deploy_create_volumes
# and
#   undeploy_remove
# are inverse operations to each other.


### Deploy


def deploy_fetch(pod):
    """Fetch images."""
    LOG.info('%s - fetch images', pod)

    cmd = ['rkt', 'image', 'list', '--fields=id', '--full', '--no-legend']
    cmd_output = scripting.execute(cmd, return_output=True)
    if cmd_output:
        cmd_output = cmd_output.decode('ascii')
        image_ids = frozenset(
            image_id
            for image_id in map(str.strip, cmd_output.split('\n'))
            if image_id
        )
    else:
        image_ids = frozenset()

    for image in pod.images:

        if match_image_id(image.id, image_ids):
            LOG.debug('skip fetching image %s', image.id)
            continue

        cmd = ['rkt', 'fetch']

        if image.signature:
            cmd.extend(['--signature', image.signature])

        if image.path:
            sig = image.signature or image.path.with_suffix('.sig')
            if not sig.is_file():
                LOG.warning('no signature for %s', image.path)
                cmd.append('--insecure-options=image')
            cmd.append(image.path)
        else:
            assert image.uri
            if image.uri.startswith('docker://'):
                cmd.append('--insecure-options=image')
            cmd.append(image.uri)

        scripting.execute(cmd)


def match_image_id(target_id, image_ids):
    for image_id in image_ids:
        if image_id.startswith(target_id) or target_id.startswith(image_id):
            return True
    return False


def deploy_install(repo, pod):
    """Install config files."""
    LOG.info('%s - install', pod)

    pod_dir = repo.get_pod_dir(pod)
    if pod_dir.exists():
        raise RuntimeError('attempt to overwrite dir: %s' % pod_dir)
    scripting.execute(['mkdir', '--parents', pod_dir], sudo=True)

    # Install pod.json.
    scripting.execute(['cp', pod.path, pod_dir / pod.POD_JSON], sudo=True)

    # Deployment-time volume allocation.
    volume_root_path = pod_dir / pod.VOLUMES_DIR
    get_volume_path = lambda volume: volume_root_path / volume.name

    # Deployment-time port allocation.
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

    # Generate Appc pod manifest.
    scripting.tee(
        pod_dir / pod.POD_MANIFEST_JSON,
        lambda output: (
            output.write(
                json.dumps(
                    pod.make_manifest(
                        get_volume_path=get_volume_path,
                        get_host_port=get_host_port,
                    ),
                    indent=4,
                    sort_keys=True,
                )
                .encode('ascii')
            ),
            output.write(b'\n'),
        ),
        sudo=True,
    )

    # Install systemd unit files.
    units_dir = pod_dir / pod.UNITS_DIR
    scripting.execute(['mkdir', '--parents', units_dir], sudo=True)
    for unit in pod.systemd_units:
        unit_path = units_dir / unit.name
        if unit_path.exists():
            raise RuntimeError('unit exists: %s' % unit_path)
        if unit.path:
            scripting.execute(['cp', unit.path, unit_path], sudo=True)
        else:
            assert unit.uri
            scripting.wget(unit.uri, unit_path, sudo=True)


def deploy_create_volumes(repo, pod):
    """Create data volumes."""
    LOG.info('%s - create data volumes', pod)
    if not pod.volumes:
        return

    volume_root_path = repo.get_pod_dir(pod) / pod.VOLUMES_DIR
    scripting.execute(['mkdir', '--parents', volume_root_path], sudo=True)

    for volume in pod.volumes:

        volume_path = volume_root_path / volume.name
        if volume_path.exists():
            raise RuntimeError('volume exists: %s' % volume_path)

        scripting.execute(['mkdir', '--parents', volume_path], sudo=True)
        cmd = [
            'chown',
            '{user}:{group}'.format(user=volume.user, group=volume.group),
            volume_path,
        ]
        scripting.execute(cmd, sudo=True)

        # Create initial contents of volume.
        if not volume.path and not volume.uri:
            continue
        with ExitStack() as stack:
            if volume.path:
                tarball_path = volume.path
            else:
                assert volume.uri
                tarball_path = (
                    Path(stack.enter_context(TemporaryDirectory())) /
                    Path(urllib.parse.urlparse(volume.uri).path).name
                )
                scripting.wget(volume.uri, tarball_path)
            scripting.tar_extract(tarball_path, sudo=True, tar_extra_args=[
                # This is the default for root, but better be explicit.
                '--preserve-permissions',
                '--directory', volume_path,
            ])


def deploy_enable(repo, pod):
    """Install and enable pod to the process manager, but might not
       start them yet.
    """
    LOG.info('%s - enable pod', pod)

    # Enable systemd units.
    pod_dir = repo.get_pod_dir(pod)
    for unit in pod.systemd_units:
        # Don't use `systemctl link` because it usually doesn't behave
        # as you expected :(
        unit_path = pod_dir / pod.UNITS_DIR / unit.name
        scripting.execute(['cp', unit_path, unit.unit_path], sudo=True)
        systemd_make_rkt_dropin(repo, pod, unit)
        for name in unit.unit_names:
            scripting.systemctl.enable(name)
            scripting.systemctl.is_enabled(name)


def systemd_make_rkt_dropin(repo, pod, unit):
    scripting.execute(['mkdir', '--parents', unit.dropin_path], sudo=True)
    scripting.tee(
        unit.dropin_path / '10-pod-manifest.conf',
        lambda output: _write_pod_manifest_dropin(repo, pod, output),
        sudo=True,
    )


def _write_pod_manifest_dropin(repo, pod, output):
    pod_dir = repo.get_pod_dir(pod)
    output.write(
        ('[Service]\n'
         'Environment="POD_MANIFEST={pod_manifest}"\n')
        .format(pod_manifest=str(pod_dir / pod.POD_MANIFEST_JSON))
        .encode('ascii')
    )


def deploy_start(pod):
    LOG.info('%s - start pod', pod)
    for unit in pod.systemd_units:
        for name in unit.unit_names:
            scripting.systemctl.start(name)
            scripting.systemctl.is_active(name)


### Undeploy


def undeploy_disable(pod):
    LOG.info('%s - disable pod', pod)

    for unit in pod.systemd_units:

        # Disable unit.
        if unit.instances:
            for instance in unit.instances:
                if scripting.systemctl.is_enabled(instance, check=False) == 0:
                    scripting.systemctl.disable(instance)
                else:
                    LOG.warning('unit is not enabled: %s', instance)
        else:
            if scripting.systemctl.is_enabled(unit.name, check=False) == 0:
                scripting.systemctl.disable(unit.name)
            else:
                LOG.warning('unit is not enabled: %s', unit.name)

        # Remove unit files.
        scripting.remove_tree(unit.unit_path)
        scripting.remove_tree(unit.dropin_path)


def undeploy_stop(pod):
    LOG.info('%s - stop pod', pod)
    for unit in pod.systemd_units:
        for name in unit.unit_names:
            if scripting.systemctl.is_active(name, check=False) == 0:
                scripting.systemctl.stop(name)
            else:
                LOG.warning('unit is not active: %s', name)


def undeploy_remove(repo, pod):
    LOG.info('%s - remove pod', pod)

    # Undo deploy_fetch.
    for image in pod.images:
        retcode = scripting.execute(
            ['rkt', 'image', 'rm', image.id], check=False)
        if retcode:
            LOG.warning('cannot safely remove image: %s (rc=%d)',
                        image.id, retcode)

    # Undo deploy_install and deploy_create_volumes.
    scripting.remove_tree(repo.get_pod_dir(pod))

    pod_parent_dir = repo.get_pod_parent_dir(pod)
    try:
        next(pod_parent_dir.iterdir())
    except StopIteration:
        scripting.execute(['rmdir', pod_parent_dir], sudo=True)


### Commands


def deploy(args):
    """Deploy a pod from a bundle."""
    repo = repos.Repo(args.ops_data)
    pod = models.Pod.load_json(args.pod_file)
    if repo.is_pod_deployed(pod):
        LOG.info('%s - pod has been deployed', pod)
        return 0
    LOG.info('%s - deploy', pod)
    try:
        deploy_fetch(pod)
        deploy_install(repo, pod)
        deploy_create_volumes(repo, pod)
    except Exception:
        undeploy_remove(repo, pod)
        raise
    return 0


deploy.help = 'deploy pod'
deploy.add_arguments_to = lambda parser: (
    parser.add_argument('pod_file', help="""path to pod file"""),
)


def start(args):
    repo = repos.Repo(args.ops_data)
    if not repo.is_pod_deployed(args.tag):
        LOG.error('%s - pod is not deployed', args.tag)
        return 1
    pod = repo.get_pod_from_tag(args.tag)
    LOG.info('%s - start', pod)
    try:
        deploy_enable(repo, pod)
        deploy_start(pod)
    except Exception:
        undeploy_stop(pod)
        undeploy_disable(pod)
        raise
    return 0


start.help = 'start pod'
start.add_arguments_to = lambda parser: (
    parser.add_argument('tag', help="""pod tag of the form 'name:version'"""),
)


def stop(args):
    """Stop a deployed pod."""
    repo = repos.Repo(args.ops_data)
    if not repo.is_pod_deployed(args.tag):
        LOG.warning('%s - pod is not deployed', args.tag)
        return 0
    pod = repo.get_pod_from_tag(args.tag)
    LOG.info('%s - stop', pod)
    undeploy_stop(pod)
    undeploy_disable(pod)
    return 0


stop.help = 'stop pod'
stop.add_arguments_to = lambda parser: (
    parser.add_argument('tag', help="""pod tag of the form 'name:version'"""),
)


def undeploy(args):
    """Undeploy a deployed pod."""
    repo = repos.Repo(args.ops_data)
    if not repo.is_pod_deployed(args.tag):
        LOG.warning('%s - pod is not deployed', args.tag)
        return 0
    pod = repo.get_pod_from_tag(args.tag)
    LOG.info('%s - undeploy', pod)
    undeploy_stop(pod)
    undeploy_disable(pod)
    undeploy_remove(repo, pod)
    return 0


undeploy.help = 'undeploy pod'
undeploy.add_arguments_to = lambda parser: (
    parser.add_argument('tag', help="""pod tag of the form 'name:version'"""),
)


def cleanup(args, repo):
    """Clean up deployed pods."""
    repo = repos.Repo(args.ops_data)
    for pod_name in repo.get_all_pod_names():
        LOG.info('%s - cleanup', pod_name)
        pods = list(repo.iter_pods_from_name(pod_name))
        num_removed = len(pods) - args.keep
        for pod in pods:
            if num_removed <= 0:
                break
            undeploy_stop(pod)
            undeploy_disable(pod)
            undeploy_remove(repo, pod)
            num_removed -= 1
    return 0


cleanup.help = 'clean up pods'
cleanup.add_arguments_to = lambda parser: (
    parser.add_argument(
        '--keep', type=int, default=7,
        help="""keep latest number of versions (default to %(default)s)"""
    ),
)
