"""Small utility commands not requiring to lock ops data directory."""

__all__ = [
    'main',
]

import json
import sys
from pathlib import Path

from ops import scripting
from ops.pods import models


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

    pod = models.Pod.load_json(args.pod_file)

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
        'pod_file', help="""path to pod file"""),
)


main = scripting.make_entity_main(
    prog='ops utils',
    description=__doc__,
    commands=[
        read_tag,
        make_manifest,
    ],
    use_ops_data=False,
)
