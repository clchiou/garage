"""Base set of commands."""

__all__ = [
    'COMMANDS',
]

import json
import sys
from pathlib import Path

from . import models


def list_pods(args):
    """List deployed pods."""
    # This is read-only; for now we don't acquire lock for it.
    repo = models.PodRepo(args.config_path, args.data_path)
    for name in repo.get_pod_names():
        version = repo.get_current_version_from_name(name)
        for pod in repo.iter_pods_from_name(name):
            print('%s%s' % (pod, ' *' if pod.version == version else ''))
    return 0


list_pods.add_arguments = models.add_arguments


def get_pod_state(args):
    """Read pod state from the pod repo."""
    # This is read-only; for now we don't acquire lock for it.
    repo = models.PodRepo(args.config_path, args.data_path)
    print(repo.get_pod_state_from_tag(args.pod_tag).value)
    return 0


get_pod_state.add_arguments = lambda parser: (
    models.add_arguments(parser),
    parser.add_argument(
        'pod_tag', help="""pod tag 'name:version'"""
    ),
)


def get_pod_tag(args):
    """Read pod tag from a pod file."""
    print(models.Pod.load_json(args.pod_file))
    return 0


get_pod_tag.add_arguments = lambda parser: (
    parser.add_argument('pod_file', help="""path to a pod file"""),
)


def list_ports(args):
    """List allocated ports."""
    # This is read-only; for now we don't acquire lock for it.
    repo = models.PodRepo(args.config_path, args.data_path)
    for port in repo.get_ports():
        print('%s:%d %s %d' %
              (port.pod_name, port.pod_version, port.name, port.port))
    return 0


list_ports.add_arguments = models.add_arguments


def make_manifest(args):
    """Generate Appc pod manifest (mostly for testing)."""

    # This is read-only; for now we don't acquire lock for it.

    repo = models.PodRepo(args.config_path, args.data_path)
    pod = repo.find_pod(args.pod)

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


make_manifest.add_arguments = lambda parser: (
    models.add_arguments(parser),
    parser.add_argument(
        '--volume', action='append',
        help="""set volume of format: volume=/path/of/volume"""),
    parser.add_argument(
        '--port', action='append',
        help="""set host port of format: port_name=port_number"""),
    parser.add_argument(
        '--output', help="""set output path (default to stdout)"""),
    parser.add_argument(
        'pod', help="""either a pod file or a pod tag 'name:version'"""
    ),
)


COMMANDS = [
    # Enumerate things
    list_pods,
    list_ports,
    # Read pod info
    get_pod_state,
    get_pod_tag,
    # Pod manifest
    make_manifest,
]
