"""Basic commands."""

__all__ = [
    'COMMANDS',
]

import json
import sys
from pathlib import Path

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
    """Generate Appc pod manifest (mostly for testing)."""
    repo = PodRepo(args.config_path, args.data_path)
    pod = repo.find_pod(args.pod)

    volume_paths = {}
    for volume_pair in args.volume or ():
        name, path = volume_pair.split('=', maxsplit=1)
        volume_paths[name] = Path(path).resolve()
    get_volume_path = lambda volume: volume_paths[volume.name]

    if args.output:
        output = open(args.output, 'w')
    else:
        output = sys.stdout
    try:
        output.write(json.dumps(
            pod.make_manifest(get_volume_path),
            indent=4,
            sort_keys=True,
        ))
        output.write('\n')
    finally:
        if output is not sys.stdout:
            output.close()


make_manifest.add_arguments = lambda parser: (
    add_arguments(parser),
    parser.add_argument(
        '--volume', action='append',
        help="""set volume of format: volume=/path/of/volume"""),
    parser.add_argument(
        '--output', help="""set output path (default to stdout)"""),
    parser.add_argument(
        'pod', help="""either a pod file or 'name:version'"""
    ),
)


COMMANDS = [
    list_pods,
    make_manifest,
]
