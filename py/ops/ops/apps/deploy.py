__all__ = [
    'COMMANDS',
]

import logging
from pathlib import Path

from ops import scripting
from ops.apps.models import ContainerGroup
from ops.scripting import systemctl


LOG = logging.getLogger(__name__)


def deploy(args):
    """Deploy a group of containers."""

    pod = make_pod(args)
    LOG.info('deploy %s:%s', pod.name, pod.version)

    # If this group of containers has not been deployed before (i.e.,
    # not a redeploy), we don't skip deploy_fetch and deploy_install.
    if not args.redeploy:
        deploy_fetch(pod)
        deploy_install(pod)

    # There should be only one active version of this container group;
    # so we stop all others before we start this version. Note:
    #
    #   * We do this right before start to reduce the service down time.
    #
    #   * We do not remove them so that you may redeploy quickly if this
    #     version fails.  The downside is, you will have to clean up the
    #     non-active versions periodically.
    #
    for other in pod.iter_pods():
        if other.version != pod.version:
            undeploy_disable(other)
            undeploy_stop(other)

    deploy_enable(pod)
    deploy_start(pod)

    return 0


# NOTE: deploy_fetch + deploy_install and undeploy_remove are inverse
# operations to each other.


def deploy_fetch(pod):
    """Fetch images."""
    LOG.info('fetch images')
    for image in pod.images:
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


def deploy_install(pod):
    """Install config files so that you may later redeploy from here."""
    LOG.info('install configs')
    # Install: bundle -> pod.config_path
    bundle_dir = pod.path.parent
    if pod.config_path.exists():
        if pod.config_path.samefile(bundle_dir):
            return
        raise RuntimeError('attempt to overwrite dir: %s' % pod.config_path)
    scripting.execute(['sudo', 'mkdir', '--parents', pod.config_path])
    scripting.execute(['sudo', 'cp', pod.path, pod.config_path / pod.POD_JSON])
    for container in pod.containers:
        if container.systemd:
            for unit in container.systemd.units:
                # Preserve directory structure.
                relpath = unit.path.relative_to(bundle_dir)
                scripting.execute(
                    ['sudo', 'cp', '--parents', relpath, pod.config_path],
                    cwd=bundle_dir,
                )
        else:
            raise AssertionError


def deploy_enable(pod):
    """Install and enable containers to the process manager, but might
       not start them yet.
    """
    LOG.info('enable containers')
    for container in pod.containers:
        if container.systemd:
            # Don't use `systemctl link` because it usually doesn't
            # behave as you expected :(
            for unit in container.systemd.units:
                scripting.execute(['sudo', 'cp', unit.path, unit.system_path])
                if unit.is_templated:
                    names = unit.instances
                else:
                    names = [unit.name]
                for name in names:
                    systemctl.enable(name)
                    systemctl.is_enabled(name)
        else:
            raise AssertionError


def deploy_start(pod):
    LOG.info('start containers')
    for container in pod.containers:
        if container.systemd:
            for service in container.systemd.services:
                systemctl.start(service)
                systemctl.is_active(service)
        else:
            raise AssertionError


def undeploy(args):
    """Undeploy a group of containers."""
    pod = make_pod(args)
    LOG.info('undeploy %s:%s', pod.name, pod.version)
    undeploy_disable(pod)
    undeploy_stop(pod)
    undeploy_remove(pod)
    return 0


def undeploy_disable(pod):
    LOG.info('disable containers')
    for container in pod.containers:
        if container.systemd:
            for unit in container.systemd.units:
                for instance in unit.instances:
                    if systemctl.is_enabled(instance, check=False) == 0:
                        systemctl.disable(instance)
                    else:
                        LOG.warning('service is not enabled: %s', instance)
                if systemctl.is_enabled(unit.name, check=False) == 0:
                    systemctl.disable(unit.name)
                else:
                    LOG.warning('service is not enabled: %s', unit.name)
                scripting.execute(['sudo', 'rm', '--force', unit.system_path])
        else:
            raise AssertionError


def undeploy_stop(pod):
    LOG.info('stop containers')
    for container in pod.containers:
        if container.systemd:
            for service in container.systemd.services:
                if systemctl.is_active(service, check=False) == 0:
                    systemctl.stop(service)
                else:
                    LOG.warning('service is not active: %s', service)
        else:
            raise AssertionError


def undeploy_remove(pod):
    LOG.info('remove configs and images')
    for image in pod.images:
        retcode = scripting.execute(
            ['sudo', 'rkt', 'image', 'rm', image.id], check=False)
        if retcode:
            LOG.warning('cannot safely remove image: %s (rc=%d)',
                        image.id, retcode)
    scripting.execute(
        ['sudo', 'rm', '--recursive', '--force', pod.config_path])


def add_arguments(parser):
    parser.add_argument(
        '--config', metavar='PATH', default='/etc/ops/apps',
        help="""path the root directory of container group configs
                (default to %(default)s)""")
    parser.add_argument(
        'path', help="""path to the container group spec file""")


def make_pod(args):
    LOG.debug('load container group spec from: %s', args.path)
    pod = ContainerGroup.load_json(args.path)

    root_config_path = Path(args.config)
    if not root_config_path.is_dir():
        scripting.execute(['sudo', 'mkdir', '--parents', root_config_path])

    pod.root_config_path = root_config_path
    LOG.debug('set config path to: %s', pod.config_path)

    if not pod.pod_config_path.is_dir():
        scripting.execute(['sudo', 'mkdir', '--parents', pod.pod_config_path])

    return pod


deploy.add_arguments = lambda parser: (
    add_arguments(parser),
    parser.add_argument(
        '--redeploy', action='store_true',
        help="""instruct a re-deploy of this container group""")
)


undeploy.add_arguments = add_arguments


COMMANDS = [
    deploy,
    undeploy,
]
