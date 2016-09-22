"""Base set of commands."""

__all__ = [
    'list_pods',
    'is_deployed',
    'read_tag',
    'make_manifest',
]

import json
import sys
from pathlib import Path

from ops.pods import models
from ops.pods import repos


def list_pods(args):
    """List deployed pods."""
    repo = repos.Repo(args.ops_data)
    for name in repo.get_all_pod_names():
        for pod in repo.iter_pods_from_name(name):
            print(pod)
    return 0


list_pods.name = 'list'
list_pods.help = 'list deployed pods'


def is_deployed(args):
    """Check if pod is deployed."""
    repo = repos.Repo(args.ops_data)
    if repo.is_pod_deployed(args.tag):
        return 0
    else:
        return 1


is_deployed.help = 'check if pod is deployed'
is_deployed.add_arguments_to = lambda parser: (
    parser.add_argument('tag', help="""pod tag of the form 'name:version'"""),
)


def read_tag(args):
    """Read pod tag from pod file."""
    print(models.Pod.load_json(args.pod_file))
    return 0


read_tag.help = 'read pod tag from pod file'
read_tag.add_arguments_to = lambda parser: (
    parser.add_argument('pod_file', help="""path to pod file"""),
)


def make_manifest(args):
    """Generate Appc pod manifest (mostly for testing)."""

    repo = repos.Repo(args.ops_data)
    if Path(args.pod).exists():
        pod = models.Pod.load_json(args.pod)
    else:
        pod = repo.get_pod_from_tag(args.pod)

    volume_paths = {}
    for volume_pair in args.volume or ():
        name, path = volume_pair.split('=', maxsplit=1)
        volume_paths[name] = Path(path).resolve()

    def get_volume_path(volume):
        try:
            return volume_paths[volume.name]
        except KeyError:
            raise ValueError('volume not found: %s' % volume.name) from None

    host_ports = {}
    for port_pair in args.port or ():
        name, port = port_pair.split('=', maxsplit=1)
        host_ports[name] = int(port)

    def get_host_port(port_name):
        try:
            return host_ports[port_name]
        except KeyError:
            raise ValueError('port not found: %s' % port_name) from None

    if args.output:
        output = open(args.output, 'w')
    else:
        output = sys.stdout
    try:
        output.write(json.dumps(
            pod.make_manifest(
                get_volume_path=get_volume_path,
                get_host_port=get_host_port,
            ),
            indent=4,
            sort_keys=True,
        ))
        output.write('\n')
    finally:
        if output is not sys.stdout:
            output.close()


make_manifest.help = 'generate appc pod manifest'
make_manifest.add_arguments_to = lambda parser: (
    parser.add_argument(
        '--volume', action='append',
        help="""set volume of format: volume=/path/of/volume"""),
    parser.add_argument(
        '--port', action='append',
        help="""set host port of format: port_name=port_number"""),
    parser.add_argument(
        '--output', help="""set output path (default to stdout)"""),
    parser.add_argument(
        'pod', help="""either pod file or a 'name:version' tag"""
    ),
)
