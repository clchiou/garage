"""Basic commands."""

__all__ = [
    'COMMANDS',
]

from ops.apps.models import ContainerGroupRepo


def add_arguments(parser):
    parser.add_argument(
        '--config', metavar='PATH', default='/etc/ops/apps',
        help="""path the root directory of container group configs
                (default to %(default)s)""")


def list_pods(args):
    """List pod names."""
    repo = ContainerGroupRepo(args.config)
    for name in repo.get_pod_names():
        for pod in repo.iter_pods_from_name(name):
            print(pod)
    return 0


list_pods.add_arguments = add_arguments


COMMANDS = [
    list_pods,
]
