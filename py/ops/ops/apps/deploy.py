"""Deployment commands."""

__all__ = [
    'COMMANDS',
]

import getpass
import logging
import os.path
import re
from subprocess import PIPE, Popen

from ops import scripting
from ops.apps import basics
from ops.apps.models import PodRepo
from ops.scripting import systemctl


LOG = logging.getLogger(__name__)


def deploy(args):
    """Deploy a pod."""

    repo = PodRepo(args.config_path, args.data_path)
    pod = repo.find_pod(args.pod)
    LOG.info('%s - deploy', pod)

    # If this pod has not been deployed before (i.e., not a redeploy),
    # we don't skip deploy_fetch, etc.
    if not args.redeploy:
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
        undeploy_disable(repo, current)
        undeploy_stop(current)

    deploy_enable(repo, pod)
    deploy_start(pod)

    return 0


# NOTE: deploy_fetch + deploy_install + deploy_create_volumes and
# undeploy_remove are inverse operations to each other.


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
            cmd.append('--signature')
            cmd.append(image.signature)
        if image.path:
            sig = image.signature or image.path.with_suffix('.sig')
            if not sig.is_file():
                LOG.warning('no signature for %s', image.path)
                cmd.append('--insecure-options=image')
            cmd.append(image.path)
        elif image.uri:
            cmd.append(image.uri)
        else:
            raise ValueError('neither "path" nor "uri" is set')
        scripting.execute(cmd)


def match_image_id(target_id, image_ids):
    for image_id in image_ids:
        if image_id.startswith(target_id) or target_id.startswith(image_id):
            return True
    return False


def deploy_install(repo, pod):
    """Install config files so that you may later redeploy from here."""
    LOG.info('%s - install configs', pod)
    # Install: bundle -> pod's config_path
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
    scripting.execute(['sudo', 'cp', pod.path, config_path / pod.POD_JSON])
    if pod.systemd:
        for unit in pod.systemd.units:
            # Preserve directory structure.
            relpath = unit.path.relative_to(bundle_path)
            scripting.execute(
                ['sudo', 'cp', '--parents', relpath, config_path],
                cwd=bundle_path,
            )
    else:
        raise AssertionError


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
            '{whoami}:{whoami}'.format(whoami=getpass.getuser()),
            volume_path,
        ])
        if volume.data:
            data = pod.path.parent / volume.data
            cmd = [
                'sudo',
                'tar',
                '--extract',
                # This is the default for root, but better be explicit.
                '--preserve-permissions',
                '--file', data,
                '--directory', volume_path,
            ]
            if scripting.is_gzipped(data):
                cmd.append('--gzip')
            scripting.execute(cmd)


def deploy_enable(repo, pod):
    """Install and enable pod to the process manager, but might not
       start them yet.
    """
    LOG.info('%s - enable pod', pod)
    if pod.systemd:
        # Don't use `systemctl link` because it usually doesn't behave
        # as you expected :(
        for unit in pod.systemd.units:
            scripting.execute(['sudo', 'cp', unit.path, unit.system_path])
            systemd_make_rkt_dropin(repo, pod, unit)
            if unit.is_templated:
                names = unit.instances
            else:
                names = [unit.name]
            for name in names:
                systemctl.enable(name)
                systemctl.is_enabled(name)
    else:
        raise AssertionError
    current_path = repo.get_current_path(pod)
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
    if not pod.images and not pod.volumes:
        return
    scripting.execute(['sudo', 'mkdir', '--parents', unit.dropin_path])
    if scripting.DRY_RUN:
        return
    if pod.images:
        _make_dropin(
            unit.dropin_path / '10-images.conf',
            lambda output: _write_image_dropin(pod.images, output),
        )
    if pod.volumes:
        _make_dropin(
            unit.dropin_path / '10-volumes.conf',
            lambda output: _write_volume_dropin(
                pod.volumes, repo.get_volume_path(pod), output),
        )


def _make_dropin(dropin_path, writer):
    with Popen(['sudo', 'tee', str(dropin_path)], stdin=PIPE) as tee:
        writer(tee.stdin)
        tee.stdin.close()
        retcode = tee.wait()
        if retcode != 0:
            raise RuntimeError('tee %s: rc=%d', dropin_path, retcode)


def _write_image_dropin(images, output):
    output.write(b'[Service]\n')
    for image in images:
        output.write(
            'Environment="IMAGE_{systemd_name}={id}"\n'.format(
                systemd_name=_to_systemd_name(image.name),
                id=image.id,
            )
            .encode('ascii')
        )


RKT_VOLUME_DROPIN = '''\
Environment="VOLUME_{systemd_name}=--volume {rkt_name},kind=host,source={source},readOnly={ro}"
Environment="MOUNT_{systemd_name}=--mount volume={rkt_name},target={target}"
Environment="MOUNT_POINT_{systemd_name}={target}"
'''


def _write_volume_dropin(volumes, volume_root_path, output):
    output.write(b'[Service]\n')
    for volume in volumes:
        output.write(
            RKT_VOLUME_DROPIN.format(
                systemd_name=_to_systemd_name(volume.name),
                rkt_name=_to_rkt_name(volume.name),
                source=str(volume_root_path / volume.name),
                target=str(volume.path),
                ro='true' if volume.read_only else 'false',
            )
            .encode('ascii')
        )


def _to_systemd_name(name):
    return re.sub(r'[\-.]', '_', name)


def _to_rkt_name(name):
    # NOTE: rkt does not accept '_' in volume name!
    return re.sub(r'[_.]', '-', name)


def deploy_start(pod):
    LOG.info('%s - start pod', pod)
    if pod.systemd:
        for service in pod.systemd.services:
            systemctl.start(service)
            systemctl.is_active(service)
    else:
        raise AssertionError


def undeploy(args):
    """Undeploy a pod."""
    repo = PodRepo(args.config_path, args.data_path)
    pod = repo.find_pod(args.pod)
    LOG.info('%s - undeploy', pod)
    undeploy_disable(repo, pod)
    undeploy_stop(pod)
    if args.remove:
        undeploy_remove(repo, pod)
    return 0


def undeploy_disable(repo, pod):
    LOG.info('%s - disable pod', pod)
    if pod.systemd:
        for unit in pod.systemd.units:
            for instance in unit.instances:
                if systemctl.is_enabled(instance, check=False) == 0:
                    systemctl.disable(instance)
                else:
                    LOG.warning('service is not enabled: %s', instance)
            if systemctl.is_enabled(unit.name, check=False) == 0:
                systemctl.disable(unit.name)
            elif not unit.is_templated:
                LOG.warning('service is not enabled: %s', unit.name)
            for path in (unit.system_path, unit.dropin_path):
                scripting.remove_tree(path)
    else:
        raise AssertionError
    if repo.get_current_version(pod) == pod.version:
        scripting.remove_tree(repo.get_current_path(pod))


def undeploy_stop(pod):
    LOG.info('%s - stop pod', pod)
    if pod.systemd:
        for service in pod.systemd.services:
            if systemctl.is_active(service, check=False) == 0:
                systemctl.stop(service)
            else:
                LOG.warning('service is not active: %s', service)
    else:
        raise AssertionError


def undeploy_remove(repo, pod):
    LOG.info('%s - remove configs and images', pod)
    for image in pod.images:
        retcode = scripting.execute(
            ['rkt', 'image', 'rm', image.id], check=False)
        if retcode:
            LOG.warning('cannot safely remove image: %s (rc=%d)',
                        image.id, retcode)
    for path in (repo.get_config_path(pod), repo.get_volume_path(pod)):
        scripting.remove_tree(path)


def cleanup(args):
    """Clean up pods that are not currently deployed."""
    repo = PodRepo(args.config_path, args.data_path)
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
    basics.add_arguments(parser)
    parser.add_argument(
        'pod', help="""either a pod spec file or 'name:version'""")


deploy.add_arguments = lambda parser: (
    add_arguments(parser),
    parser.add_argument(
        '--redeploy', action='store_true',
        help="""instruct a re-deploy of this pod""")
)


undeploy.add_arguments = lambda parser: (
    add_arguments(parser),
    parser.add_argument(
        '--remove', action='store_true',
        help="""remove pod data""")
)


cleanup.add_arguments = lambda parser: (
    basics.add_arguments(parser),
    parser.add_argument(
        '--keep', type=int, default=1,
        help="""keep latest N versions (default to %(default)s)""")
)


COMMANDS = [
    deploy,
    undeploy,
    cleanup,
]
