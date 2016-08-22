"""Basic commands."""

__all__ = [
    'COMMANDS',
]

import json
import sys

from ops.apps.models import PodRepo


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
    repo = PodRepo(args.config_path, args.data_path)
    for name in repo.get_pod_names():
        version = repo.get_current_version_from_name(name)
        for pod in repo.iter_pods_from_name(name):
            print('%s%s' % (pod, ' *' if pod.version == version else ''))
    return 0


list_pods.add_arguments = add_arguments


def make_manifest(args):
    """Generate Appc pod manifest."""
    repo = PodRepo(args.config_path, args.data_path)
    pod = repo.find_pod(args.pod)
    sys.stdout.write(json.dumps(
        pod.make_manifest(repo),
        indent=4,
        sort_keys=True,
    ))
    sys.stdout.write('\n')


make_manifest.add_arguments = lambda parser: (
    add_arguments(parser),
    parser.add_argument(
        'pod', help="""either a pod file or 'name:version'"""
    ),
)


COMMANDS = [
    list_pods,
    make_manifest,
]
