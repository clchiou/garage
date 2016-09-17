"""Deployment commands."""

__all__ = [
    'COMMANDS',
]

import json
import logging
import os.path
import urllib.parse
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

from ops import scripting
from ops.apps import models


LOG = logging.getLogger(__name__)


@models.require_repo_lock
def deploy(args, repo):
    """Deploy a pod."""
    with ExitStack() as rollback:
        return _deploy(args, repo, rollback)


def _deploy(args, repo, rollback):

    pod = repo.find_pod(args.pod)
    LOG.info('%s - deploy', pod)

    pod_state = repo.get_pod_state(pod)
    if pod_state is pod.State.CURRENT:
        LOG.info('%s - pod is current', pod)
        return 0
    elif pod_state is pod.State.DEPLOYED:
        pass
    else:
        assert pod_state is pod.State.UNDEPLOYED  # Sanity check.
        rollback.callback(undeploy_remove, repo, pod)
        deploy_fetch(pod)
        deploy_install(repo, pod)
        deploy_create_volumes(repo, pod)

    # There should be only one active version of this pod.
    # Note that:
    #
    #   * We do this right before start to reduce the service down time.
    #
    #   * We do not remove them so that you may redeploy quickly if this
    #     version fails.  The downside is, you will have to clean up the
    #     non-active versions periodically.
    #
    current = repo.get_current_pod(pod)
    if current is not None:
        # Don't add rollback for these two operations; we don't want to
        # automatically revert to the previous deployment on failure, at
        # least not for now.
        undeploy_disable(repo, current)
        undeploy_stop(current)

    rollback.callback(undeploy_disable, repo, pod)
    deploy_enable(repo, pod)

    rollback.callback(undeploy_stop, pod)
    deploy_start(pod)

    rollback.pop_all()  # Clear rollback stack on success.
    return 0


# Note that
#   deploy_fetch + deploy_install + deploy_create_volumes
# and
#   undeploy_remove
# are inverse operations to each other.


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
    """Install config files so that you may later redeploy from here."""
    LOG.info('%s - install configs', pod)

    bundle_path = pod.path.parent
    config_path = repo.get_config_path(pod)
    if config_path.exists():
        if config_path.samefile(bundle_path):
            # If you are here, it means that you are deploying from
            # installed config files, and you don't need to reinstall
            # them again.
            return
        raise RuntimeError('attempt to overwrite dir: %s' % config_path)
    scripting.execute(['sudo', 'mkdir', '--parents', config_path])

    # Install pod.json.
    scripting.execute(['sudo', 'cp', pod.path, config_path / pod.POD_JSON])

    # Deployment-time volume allocation.
    volume_root_path = repo.get_volume_path(pod)
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
        config_path / pod.POD_MANIFEST_JSON,
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
    units_dir = config_path / pod.UNITS_DIR
    scripting.execute(['sudo', 'mkdir', '--parents', units_dir])
    for unit in pod.systemd_units:
        unit_path = units_dir / unit.name
        if unit_path.exists():
            LOG.warning('unit exists: %s', unit_path)
            continue
        if unit.path:
            scripting.execute(['sudo', 'cp', unit.path, unit_path])
        else:
            assert unit.uri
            scripting.wget(unit.uri, unit_path, sudo=True)


def deploy_create_volumes(repo, pod):
    """Create data volumes."""
    LOG.info('%s - create data volumes', pod)
    if not pod.volumes:
        return

    volume_root_path = repo.get_volume_path(pod)

    for volume in pod.volumes:

        volume_path = volume_root_path / volume.name
        if volume_path.exists():
            LOG.warning('volume exists: %s', volume_path)
            continue

        scripting.execute(['sudo', 'mkdir', '--parents', volume_path])
        scripting.execute([
            'sudo',
            'chown',
            '{user}:{group}'.format(user=volume.user, group=volume.group),
            volume_path,
        ])

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

    # Check if there is a pod currently enabled.
    current_path = repo.get_current_path(pod)
    if current_path.exists():
        raise RuntimeError('attempt to overwrite: %s' % current_path)

    # Enable systemd units.
    config_path = repo.get_config_path(pod)
    for unit in pod.systemd_units:
        # Don't use `systemctl link` because it usually doesn't behave
        # as you expected :(
        unit_path = config_path / pod.UNITS_DIR / unit.name
        scripting.execute(['sudo', 'cp', unit_path, unit.unit_path])
        systemd_make_rkt_dropin(repo, pod, unit)
        for name in unit.unit_names:
            scripting.systemctl.enable(name)
            scripting.systemctl.is_enabled(name)

    # Mark this pod as the current one.
    scripting.execute(['sudo', 'mkdir', '--parents', current_path.parent])
    scripting.execute([
        'sudo', 'ln', '--symbolic',
        # Unfortunately Path.relative_to doesn't work in this case.
        os.path.relpath(
            str(repo.get_config_path(pod)),
            str(current_path.parent),
        ),
        current_path,
    ])


def systemd_make_rkt_dropin(repo, pod, unit):
    scripting.execute(['sudo', 'mkdir', '--parents', unit.dropin_path])
    scripting.tee(
        unit.dropin_path / '10-pod-manifest.conf',
        lambda output: _write_pod_manifest_dropin(repo, pod, output),
        sudo=True,
    )


def _write_pod_manifest_dropin(repo, pod, output):
    config_path = repo.get_config_path(pod)
    output.write(
        ('[Service]\n'
         'Environment="POD_MANIFEST={pod_manifest}"\n')
        .format(pod_manifest=str(config_path / pod.POD_MANIFEST_JSON))
        .encode('ascii')
    )


def deploy_start(pod):
    LOG.info('%s - start pod', pod)
    for unit in pod.systemd_units:
        if unit.start:
            for name in unit.unit_names:
                scripting.systemctl.start(name)
                scripting.systemctl.is_active(name)


@models.require_repo_lock
def undeploy(args, repo):
    """Undeploy a pod."""
    pod = repo.find_pod(args.pod)
    LOG.info('%s - undeploy', pod)
    undeploy_stop(pod)
    undeploy_disable(repo, pod)
    if args.remove:
        undeploy_remove(repo, pod)
    return 0


def undeploy_disable(repo, pod):
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

    # Unmark this pod as the current one.
    if repo.get_current_version(pod) == pod.version:
        scripting.remove_tree(repo.get_current_path(pod))


def undeploy_stop(pod):
    LOG.info('%s - stop pod', pod)
    for unit in pod.systemd_units:
        if unit.start:
            for name in unit.unit_names:
                if scripting.systemctl.is_active(name, check=False) == 0:
                    scripting.systemctl.stop(name)
                else:
                    LOG.warning('unit is not active: %s', name)


def undeploy_remove(repo, pod):
    LOG.info('%s - remove configs and images', pod)

    # Undo deploy_fetch.
    for image in pod.images:
        retcode = scripting.execute(
            ['rkt', 'image', 'rm', image.id], check=False)
        if retcode:
            LOG.warning('cannot safely remove image: %s (rc=%d)',
                        image.id, retcode)

    # Undo deploy_install.
    scripting.remove_tree(repo.get_config_path(pod))

    # Undo deploy_create_volumes.
    scripting.remove_tree(repo.get_volume_path(pod))


@models.require_repo_lock
def cleanup(args, repo):
    """Clean up pods that are not currently deployed."""
    for pod_name in repo.get_pod_names():
        LOG.info('%s - cleanup', pod_name)
        version = repo.get_current_version_from_name(pod_name)
        pods = list(repo.iter_pods_from_name(pod_name))
        num_removed = len(pods) - args.keep
        for pod in pods:
            if pod.version == version:
                continue  # Don't clean up the currently deployed one.
            if num_removed <= 0:
                break
            undeploy_disable(repo, pod)
            undeploy_stop(pod)
            undeploy_remove(repo, pod)
            num_removed -= 1
    return 0


def add_arguments(parser):
    models.add_arguments(parser)
    parser.add_argument(
        'pod', help="""either a pod file or a pod tag 'name:version'""")


deploy.add_arguments = add_arguments


undeploy.add_arguments = lambda parser: (
    add_arguments(parser),
    parser.add_argument(
        '--remove', action='store_true',
        help="""remove pod data"""
    ),
)


cleanup.add_arguments = lambda parser: (
    models.add_arguments(parser),
    parser.add_argument(
        '--keep', type=int, default=1,
        help="""keep latest N versions (default to %(default)s)"""
    ),
)


COMMANDS = [
    deploy,
    undeploy,
    cleanup,
]
