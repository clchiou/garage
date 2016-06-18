"""Basic commands."""

__all__ = [
    'COMMANDS',
]

from ops.apps.models import ContainerGroupRepo


def add_arguments(parser):
    parser.add_argument(
        '--config-path', metavar='PATH', default='/etc/ops/apps',
        help="""path the root directory of container group configs
                (default to %(default)s)""")
    parser.add_argument(
        '--data-path', metavar='PATH', default='/var/lib/ops/apps',
        help="""path the root directory of container group data
                (default to %(default)s)""")


def list_pods(args):
    """List pod names."""
    repo = ContainerGroupRepo(args.config_path, args.data_path)
    for name in repo.get_pod_names():
        version = repo.get_current_version_from_name(name)
        for pod in repo.iter_pods_from_name(name):
            print('%s%s' % (pod, ' *' if pod.version == version else ''))
    return 0


list_pods.add_arguments = add_arguments


COMMANDS = [
    list_pods,
]
